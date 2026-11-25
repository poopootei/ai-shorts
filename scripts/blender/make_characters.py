"""自前の人形（老若男女）を Blender の中で作り、glb に書き出す（docs/decisions.md D-029）。

    D:\\blender\\blender.exe -b --factory-startup -P scripts/blender/make_characters.py -- [--only young_man,old_woman] [--preview DIR]

- 形はメタボール（球・楕円体を溶け合わせる）で作る。外部の素材は使わない。数値は SPECS に書く。
- 長さの単位は「頭の高さ」（hh）。身長 H を heads（頭身）で割ったものが 1hh。
- 骨は Mixamo と同じ名前で T ポーズ（kit の RIGS["own"]）。Mixamo の動きもそのまま移せる。
- 顔（目・まゆ・口）は形状キーで表情を変える：blink / smile / open / surprise / angry / sad（kit の Character.expr）
- 材質の名前（skin / hair / top / inner / bottom / shoes / detail …）は、kit の recolor で物語ごとに色を変えられる。
出力：assets/3d/characters/own_{name}.glb。--preview DIR で、並べた絵（正面・斜め・表情）を DIR に書く。
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "assets" / "3d" / "characters"

BALL_K = 0.575     # メタボールの球（radius 1）の見た目の半径
CHAIN_K = 0.715    # 0.25R 間隔で並べた球の列の見た目の半径


def srgb(h: str):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


# ---- 人形の数値 ------------------------------------------------------------------
# 体の幅・太さは hh。arm_r = 肩・ひじ・前腕・手首、leg_r = もも・ひざ・ふくらはぎ・足首の半径。
# hand = 長さ・幅・厚み、foot = 長さ・幅・高さ。head / jaw = 頭・あごの楕円体の半径（x, y, z）。
# 顔の位置は顔の中心（あごから 0.5hh 上）からの x, z。

BASE = dict(
    heads=5.4, sh_x=0.74, chest=(0.60, 0.40, 0.45), waist=(0.50, 0.35, 0.42), pelvis=(0.54, 0.38, 0.36),
    bust=0.0, belly=0.0, neck_r=0.15, arm_r=(0.17, 0.135, 0.145, 0.11), leg_x=0.25,
    leg_r=(0.25, 0.17, 0.185, 0.115), hand=(0.46, 0.27, 0.13), foot=(0.72, 0.27, 0.24),
    head=(0.44, 0.45, 0.50), jaw=(0.36, 0.36, 0.28), nose=0.05, ears=True,
    eye=dict(x=0.165, z=-0.05, w=0.075, h=0.11, hl=True), brow=dict(z=0.12, len=0.14, t=0.022, arch=0.02, tilt=0.0),
    mouth=dict(z=-0.27, w=0.11, t=0.016, smile=0.03), blush=False, lashes=False,
    hair="short", glasses=False, mustache=False,
    sleeve=1.0, top_hem=-0.1, bottom="pants", pants_hem=None, skirt_hem=None, flare=0.25,
    v_neck=None, buttons=0, hood=False, collar=False, cuffs=True, rolled=False,
    colors=dict(skin="#F2C8A6", hair="#2B1D16", top="#E9A23B", inner="#F4F1EA", bottom="#33476E",
                shoes="#F0EFEA", eye="#1A1414", mouth="#9A3A3A", glass="#3C3434", cheek="#F2A0A0",
                detail="#5A4636", lip="#B3473F"),
)

SPECS = {
    # 若い男：パーカー・ジーンズ・白いスニーカー。短い黒髪
    "young_man": dict(
        label="若い男", H=1.72, heads=5.4, sh_x=0.76, hair="short", hood=True, rolled=True,
        top_hem=-0.16,
        colors=dict(top="#E39B2E", inner="#F4F1EA", bottom="#2F4A78", shoes="#F2F2EE", hair="#231914"),
    ),
    # 若い女：半そでのブラウス・ひざ丈のスカート。ボブ
    "young_woman": dict(
        label="若い女", H=1.60, heads=5.3, sh_x=0.62, chest=(0.54, 0.37, 0.44), waist=(0.42, 0.31, 0.40),
        pelvis=(0.55, 0.39, 0.37), bust=0.13, neck_r=0.13, arm_r=(0.145, 0.115, 0.125, 0.095),
        leg_x=0.24, leg_r=(0.25, 0.155, 0.17, 0.10), hand=(0.42, 0.24, 0.12), foot=(0.64, 0.23, 0.2),
        head=(0.43, 0.45, 0.50), jaw=(0.34, 0.35, 0.27),
        eye=dict(x=0.165, z=-0.05, w=0.078, h=0.12, hl=True), brow=dict(z=0.125, len=0.13, t=0.017, arch=0.025, tilt=0.0),
        mouth=dict(z=-0.27, w=0.095, t=0.016, smile=0.03), blush=True, lashes=True,
        hair="bob", sleeve=0.42, collar=True, top_hem=0.05, bottom="skirt", skirt_hem=0.15, flare=0.32,
        colors=dict(top="#F07C6C", bottom="#2B3A5C", shoes="#7A4A30", hair="#3A2418", mouth="#B3473F"),
    ),
    # 年配の男：カーディガン・シャツ・スラックス。はげ頭・白髪・眼鏡・口ひげ
    "old_man": dict(
        label="年配の男", H=1.66, heads=5.3, sh_x=0.72, chest=(0.60, 0.42, 0.45), waist=(0.56, 0.44, 0.42),
        pelvis=(0.56, 0.42, 0.36), belly=0.12, arm_r=(0.165, 0.13, 0.14, 0.105),
        head=(0.44, 0.46, 0.49), jaw=(0.37, 0.37, 0.29),
        eye=dict(x=0.165, z=-0.05, w=0.06, h=0.075, hl=True), brow=dict(z=0.165, len=0.15, t=0.03, arch=0.01, tilt=-0.02),
        mouth=dict(z=-0.29, w=0.10, t=0.015, smile=0.02),
        hair="bald", glasses=True, mustache=True, v_neck=dict(bottom=-0.75, w=0.2), buttons=4, top_hem=-0.2,
        colors=dict(top="#6E7448", inner="#EDEBE4", bottom="#55565C", shoes="#3A2A20", hair="#D9D6D0",
                    detail="#3B3A2A"),
    ),
    # 年配の女：カーディガン・ブラウス・スラックス。白髪のおだんご・眼鏡
    "old_woman": dict(
        label="年配の女", H=1.52, heads=5.0, sh_x=0.62, chest=(0.56, 0.41, 0.44), waist=(0.52, 0.40, 0.40),
        pelvis=(0.58, 0.42, 0.37), bust=0.10, belly=0.06, neck_r=0.13, arm_r=(0.15, 0.12, 0.13, 0.095),
        leg_x=0.24, leg_r=(0.25, 0.16, 0.17, 0.10), hand=(0.40, 0.24, 0.12), foot=(0.62, 0.23, 0.2),
        head=(0.43, 0.45, 0.49), jaw=(0.35, 0.36, 0.28),
        eye=dict(x=0.16, z=-0.05, w=0.06, h=0.075, hl=True), brow=dict(z=0.165, len=0.12, t=0.022, arch=0.02, tilt=0.0),
        mouth=dict(z=-0.28, w=0.09, t=0.015, smile=0.03), blush=True,
        hair="bun", glasses=True, v_neck=dict(bottom=-0.7, w=0.18), buttons=4, top_hem=-0.12,
        colors=dict(top="#8E5A86", inner="#F3EEE8", bottom="#8B8274", shoes="#4A3A33", hair="#DCD8D4",
                    detail="#5C3657", glass="#7A5A3A", cheek="#EBA0A0"),
    ),
}


def spec_of(name: str) -> dict:
    s = {k: (dict(v) if isinstance(v, dict) else v) for k, v in BASE.items()}
    for k, v in SPECS[name].items():
        if isinstance(v, dict) and isinstance(s.get(k), dict):
            s[k].update(v)
        else:
            s[k] = v
    s["name"] = name
    return s


# ---- 道具 ------------------------------------------------------------------------

def col():
    return bpy.context.scene.collection


def make_material(name, hexcolor, rough=0.6, spec=0.3):
    m = bpy.data.materials.new(name)
    if m.node_tree is None:
        m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*srgb(hexcolor), 1)
    bsdf.inputs["Roughness"].default_value = rough
    try:
        bsdf.inputs["Specular IOR Level"].default_value = spec
    except KeyError:
        pass
    return m


def apply_modifiers(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    old = obj.data
    obj.modifiers.clear()
    obj.data = me
    bpy.data.meshes.remove(old)


def mesh_object(name, bm, mat=None, groups=None, smooth=True):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    if smooth:
        me.shade_smooth()
    o = bpy.data.objects.new(name, me)
    col().objects.link(o)
    if mat:
        me.materials.append(mat)
    for g, w in (groups or {}).items():
        vg = o.vertex_groups.new(name=g)
        vg.add(list(range(len(me.vertices))), w, "REPLACE")
    return o


def sphere_bm(matrix, segs=20, rings=10):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=rings, radius=1.0)
    bmesh.ops.transform(bm, matrix=matrix, verts=bm.verts)
    return bm


def sweep(bm, pts, radii, closed=False, up=None, prof=10, ell=(1.0, 1.0)):
    """折れ線 pts にそって管を作る（半径 radii）。up を渡すと断面の向きを固定する（帯など）。"""
    n = len(pts)
    tans = []
    for i in range(n):
        a = pts[i - 1] if (closed or i > 0) else pts[i]
        b = pts[(i + 1) % n] if (closed or i < n - 1) else pts[i]
        tans.append((b - a).normalized())
    frames = []
    if up is not None:
        for t in tans:
            nr = t.cross(up).normalized()
            frames.append((nr, nr.cross(t).normalized()))
    else:
        t0 = tans[0]
        ref = Vector((0, 0, 1)) if abs(t0.z) < 0.9 else Vector((1, 0, 0))
        nr = (ref - t0 * ref.dot(t0)).normalized()
        for t in tans:
            nr = (nr - t * nr.dot(t)).normalized()
            frames.append((nr, t.cross(nr)))
    rings = []
    for p, (nr, bi), r in zip(pts, frames, radii):
        rings.append([bm.verts.new(p + nr * (r * ell[0] * math.cos(a)) + bi * (r * ell[1] * math.sin(a)))
                      for a in (2 * math.pi * k / prof for k in range(prof))])
    for i in range(n if closed else n - 1):
        A, B = rings[i], rings[(i + 1) % n]
        for k in range(prof):
            bm.faces.new((A[k], A[(k + 1) % prof], B[(k + 1) % prof], B[k]))
    if not closed:
        bm.faces.new(list(reversed(rings[0])))
        bm.faces.new(rings[-1])


def frame_from_normal(n, up=Vector((0, 0, 1))):
    """面の法線 n から向きの行列（x = 横、y = 面の奥、z = 上）。"""
    y = -n.normalized()
    z = (up - y * up.dot(y)).normalized()
    x = y.cross(z)
    return Matrix((x, y, z)).transposed()


class Meta:
    """メタボール。大きさは「見た目の半径」で渡す。"""

    def __init__(self, name, res):
        self.mb = bpy.data.metaballs.new(name)
        self.mb.resolution = res
        self.mb.render_resolution = res
        self.mb.threshold = 0.6
        self.obj = bpy.data.objects.new(name, self.mb)
        col().objects.link(self.obj)

    def ball(self, c, r, neg=False):
        e = self.mb.elements.new(type="BALL")
        e.co = c
        e.radius = r / BALL_K
        e.use_negative = neg

    def ell(self, c, size, rot=None, neg=False):
        e = self.mb.elements.new(type="ELLIPSOID")
        e.co = c
        e.radius = 1.0
        e.size_x, e.size_y, e.size_z = (s / BALL_K for s in size)
        if rot is not None:
            e.rotation = rot
        e.use_negative = neg

    def chain(self, pts_r):
        """[(点, 半径), …] を、半径を補間しながら球でつなぐ。"""
        for (p0, r0), (p1, r1) in zip(pts_r, pts_r[1:]):
            p0, p1 = Vector(p0), Vector(p1)
            L = (p1 - p0).length
            R = min(r0, r1) / CHAIN_K
            n = max(2, int(L / (0.25 * R)) + 1)
            for i in range(n):
                t = i / (n - 1)
                e = self.mb.elements.new(type="BALL")
                e.co = p0.lerp(p1, t)
                e.radius = (r0 + (r1 - r0) * t) / CHAIN_K

    def to_mesh(self, name):
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(self.obj.evaluated_get(dg))
        bpy.data.objects.remove(self.obj)
        bpy.data.metaballs.remove(self.mb)
        o = bpy.data.objects.new(name, me)
        col().objects.link(o)
        return o


# ---- 人形を作る -----------------------------------------------------------------------

class Builder:
    def __init__(self, s: dict):
        self.s = s
        self.hh = s["H"] / s["heads"]
        B = s["heads"] - 1.0
        self.B = B
        L = dict(chin=B, sh_z=0.93 * B, chest_z=0.84 * B, waist_z=0.71 * B, hips_z=0.61 * B,
                 leg_z=0.555 * B, knee_z=0.29 * B, ankle_z=0.045 * B)
        L["neck_base"] = L["sh_z"] + 0.1
        L["elbow_x"] = s["sh_x"] + 0.19 * B
        L["wrist_x"] = L["elbow_x"] + 0.17 * B
        L["face_z"] = B + 0.5
        self.L = L
        self.mats = {}
        self.parts = []

    def v(self, x, y, z):
        return Vector((x, y, z)) * self.hh

    # 材質 --------------------------------------------------------------------
    def mat(self, key):
        if key not in self.mats:
            c = self.s["colors"]
            rough = {"eye": 0.15, "glass": 0.3, "eye_hl": 0.3, "mouth": 0.5, "skin": 0.55, "hair": 0.5}.get(key, 0.7)
            hexc = {"eye_hl": "#FFFFFF", "brow": c["hair"]}.get(key) or c[key]
            self.mats[key] = make_material(key, hexc, rough=rough)
        return self.mats[key]

    # 骨 ----------------------------------------------------------------------
    def armature(self):
        s, L, v = self.s, self.L, self.v
        data = bpy.data.armatures.new(f"{s['name']}_rig")
        arm = bpy.data.objects.new(f"{s['name']}_rig", data)
        col().objects.link(arm)
        bpy.context.view_layer.objects.active = arm
        arm.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        eb = data.edit_bones
        bones = {}

        def bone(name, head, tail, parent=None, connect=False, deform=True):
            b = eb.new(name)
            b.head, b.tail = head, tail
            if parent:
                b.parent = bones[parent]
                b.use_connect = connect
            b.use_deform = deform
            bones[name] = b
            return b

        hz = L["hips_z"]
        s0, s3 = hz + 0.2, L["neck_base"]
        d = (s3 - s0) / 3
        bone("Hips", v(0, 0.02, hz), v(0, 0.02, s0))
        bone("Spine", v(0, 0.02, s0), v(0, 0.02, s0 + d), "Hips", True)
        bone("Spine1", v(0, 0.02, s0 + d), v(0, 0.02, s0 + 2 * d), "Spine", True)
        bone("Spine2", v(0, 0.02, s0 + 2 * d), v(0, 0.02, s3), "Spine1", True)
        bone("Neck", v(0, 0.03, s3), v(0, 0.03, L["chin"] + 0.12), "Spine2", True)
        bone("Head", v(0, 0.03, L["chin"] + 0.12), v(0, 0.03, L["chin"] + 1.05), "Neck", True)
        bone("HeadTop_End", v(0, 0.03, L["chin"] + 1.05), v(0, 0.03, L["chin"] + 1.2), "Head", True, deform=False)
        hl, hw = s["hand"][0], s["hand"][1]
        for S, k in (("Left", 1), ("Right", -1)):
            sh, el, wr = s["sh_x"], L["elbow_x"], L["wrist_x"]
            z = L["sh_z"]
            bone(f"{S}Shoulder", v(k * 0.12, 0.0, z + 0.04), v(k * sh, 0.02, z), "Spine2")
            bone(f"{S}Arm", v(k * sh, 0.02, z), v(k * el, 0.04, z), f"{S}Shoulder", True)
            bone(f"{S}ForeArm", v(k * el, 0.04, z), v(k * wr, 0.02, z), f"{S}Arm", True)
            bone(f"{S}Hand", v(k * wr, 0.02, z), v(k * (wr + 0.5 * hl), 0.0, z), f"{S}ForeArm", True)
            prev = f"{S}Hand"
            xs = [wr + 0.5 * hl, wr + 0.67 * hl, wr + 0.83 * hl, wr + 0.97 * hl, wr + 1.1 * hl]
            for i in range(4):
                n = f"{S}HandIndex{i + 1}"
                bone(n, v(k * xs[i], -0.02, z), v(k * xs[i + 1], -0.02, z), prev, i > 0, deform=i < 3)
                prev = n
            prev = f"{S}Hand"
            t0 = Vector((wr + 0.08, -0.25 * hw, z - 0.01))
            t1 = Vector((wr + 0.30, -0.66 * hw, z - 0.02))
            for i in range(4):
                n = f"{S}HandThumb{i + 1}"
                a, b = t0.lerp(t1, i / 3), t0.lerp(t1, (i + 1) / 3) if i < 3 else t1 + (t1 - t0) * 0.15
                bone(n, v(k * a.x, a.y, a.z), v(k * b.x, b.y, b.z), prev, i > 0, deform=i < 3)
                prev = n
            lx = s["leg_x"]
            bone(f"{S}UpLeg", v(k * lx, 0.02, L["leg_z"]), v(k * lx, -0.01, L["knee_z"]), "Hips")
            bone(f"{S}Leg", v(k * lx, -0.01, L["knee_z"]), v(k * lx, 0.03, L["ankle_z"]), f"{S}UpLeg", True)
            fl = s["foot"][0]
            bone(f"{S}Foot", v(k * lx, 0.03, L["ankle_z"]), v(k * lx, -0.38 * fl, 0.06), f"{S}Leg", True)
            bone(f"{S}ToeBase", v(k * lx, -0.38 * fl, 0.06), v(k * lx, -0.72 * fl, 0.05), f"{S}Foot", True)
            bone(f"{S}Toe_End", v(k * lx, -0.72 * fl, 0.05), v(k * lx, -0.85 * fl, 0.05), f"{S}ToeBase", True,
                 deform=False)
        bpy.ops.object.mode_set(mode="OBJECT")
        arm.select_set(False)
        self.arm = arm
        return arm

    # 体 ----------------------------------------------------------------------
    def body(self):
        s, L, v = self.s, self.L, self.v
        m = Meta(f"{s['name']}_bodyMB", 0.018 * self.hh)
        B = self.B
        # 胴
        m.ell(v(0, 0.02, L["chest_z"]), [x * self.hh for x in s["chest"]])
        m.ell(v(0, 0.02, L["waist_z"]), [x * self.hh for x in s["waist"]])
        m.ell(v(0, 0.03, L["hips_z"]), [x * self.hh for x in s["pelvis"]])
        m.chain([(v(-s["sh_x"], 0.02, L["sh_z"] - 0.04), s["arm_r"][0] * self.hh),
                 (v(s["sh_x"], 0.02, L["sh_z"] - 0.04), s["arm_r"][0] * self.hh)])
        if s["bust"]:
            b = s["bust"]
            for k in (1, -1):
                m.ell(v(k * 0.19, -0.2, L["chest_z"] - 0.06), [b * self.hh, b * 0.85 * self.hh, b * 0.9 * self.hh])
        if s["belly"]:
            m.ell(v(0, -0.12, L["waist_z"] - 0.08), [0.42 * self.hh, (0.3 + s["belly"]) * self.hh, 0.38 * self.hh])
        # 首
        m.chain([(v(0, 0.04, L["sh_z"] - 0.1), s["neck_r"] * self.hh), (v(0, 0.04, B + 0.25), s["neck_r"] * self.hh)])
        # 腕・手
        ar = s["arm_r"]
        hl, hw, ht = s["hand"]
        for k in (1, -1):
            sh, el, wr, z = s["sh_x"], L["elbow_x"], L["wrist_x"], L["sh_z"]
            m.chain([(v(k * sh, 0.02, z), ar[0] * self.hh), (v(k * el, 0.04, z), ar[1] * self.hh),
                     (v(k * (el + 0.3 * (wr - el)), 0.03, z), ar[2] * self.hh), (v(k * wr, 0.02, z), ar[3] * self.hh)])
            m.ell(v(k * (wr + hl * 0.52), 0.0, z), [hl * 0.5 * self.hh, hw * 0.5 * self.hh, ht * 0.5 * self.hh])
            m.chain([(v(k * (wr + 0.08), -0.25 * hw, z - 0.01), 0.05 * self.hh),
                     (v(k * (wr + 0.30), -0.66 * hw, z - 0.02), 0.042 * self.hh)])
        # 脚・足
        lr = s["leg_r"]
        fl, fw, fh = s["foot"]
        for k in (1, -1):
            lx = s["leg_x"]
            m.chain([(v(k * lx, 0.03, L["leg_z"] + 0.05), lr[0] * self.hh), (v(k * lx, 0.0, L["knee_z"]), lr[1] * self.hh),
                     (v(k * lx, 0.04, L["knee_z"] - 0.32), lr[2] * self.hh), (v(k * lx, 0.03, L["ankle_z"] + 0.05), lr[3] * self.hh)])
            m.ell(v(k * lx, -fl * 0.28, fh * 0.5), [fw * 0.5 * self.hh, fl * 0.5 * self.hh, fh * 0.5 * self.hh])
        # 頭
        hx, hy, hz = s["head"]
        m.ell(v(0, 0.03, B + 0.55), [hx * self.hh, hy * self.hh, hz * self.hh])
        jx, jy, jz = s["jaw"]
        m.ell(v(0, -0.03, B + 0.30), [jx * self.hh, jy * self.hh, jz * self.hh])
        m.ball(v(0, -0.40, B + 0.34), s["nose"] * self.hh)
        if s["ears"]:
            for k in (1, -1):
                m.ell(v(k * hx * 0.96, 0.06, B + 0.45), [0.05 * self.hh, 0.09 * self.hh, 0.12 * self.hh])
        o = m.to_mesh(s["name"])
        dec = o.modifiers.new("decimate", "DECIMATE")
        dec.ratio = 0.3
        apply_modifiers(o)
        sm = o.modifiers.new("smooth", "SMOOTH")
        sm.factor = 0.5
        sm.iterations = 3
        apply_modifiers(o)
        o.data.shade_smooth()
        self.body_obj = o
        dg = bpy.context.evaluated_depsgraph_get()
        self.bvh = BVHTree.FromObject(o, dg)
        return o

    # 服の色分け ------------------------------------------------------------------
    def paint(self):
        s, L = self.s, self.L
        o = self.body_obj
        keys = ["skin", "top", "inner", "bottom", "shoes"]
        for k in keys:
            o.data.materials.append(self.mat(k))
        idx = {k: i for i, k in enumerate(keys)}
        sh, wr = s["sh_x"], L["wrist_x"]
        shoe_top = s["foot"][2] + 0.04
        top_hem = L["hips_z"] + s["top_hem"]
        pants_hem = s["pants_hem"] if s["pants_hem"] is not None else shoe_top - 0.02
        vn = s["v_neck"]
        for p in o.data.polygons:
            c = p.center / self.hh
            ax = abs(c.x)
            if c.z < shoe_top and ax > s["leg_x"] - s["foot"][1] and c.z < L["ankle_z"] + 0.12:
                k = "shoes"
            elif c.z > L["chin"] + 0.03 or (c.z > L["neck_base"] - 0.02 and ax < s["neck_r"] * 1.35):
                k = "skin"
            elif ax > sh * 0.97 and c.z > L["sh_z"] - 0.45:
                t = (ax - sh) / (wr - sh)
                k = "skin" if (ax > wr - 0.02 or t > s["sleeve"]) else "top"
            elif c.z > top_hem:
                k = "top"
                if vn and c.y < 0 and c.z > L["neck_base"] + vn["bottom"]:
                    f = (c.z - (L["neck_base"] + vn["bottom"])) / -vn["bottom"]
                    if ax < vn["w"] * f:
                        k = "inner"
            elif s["bottom"] == "skirt":
                k = "bottom" if c.z > L["leg_z"] - 0.1 else "skin"
            else:
                k = "bottom" if c.z > pants_hem else "skin"
            p.material_index = idx[k]

    # 顔 ------------------------------------------------------------------------
    def hit_front(self, x, z):
        loc, n, _, _ = self.bvh.ray_cast(self.v(x, -3.0, z), Vector((0, 1, 0)), 10.0)
        if loc is None:
            raise RuntimeError(f"顔の位置が見つかりません: x={x} z={z}")
        return loc, n

    def add(self, name, bm, mat, groups):
        o = mesh_object(f"{self.s['name']}_{name}", bm, self.mat(mat), groups)
        self.parts.append(o)
        return o

    def face(self):
        s, L, hh = self.s, self.L, self.hh
        fz = L["face_z"]
        e, br, mo = s["eye"], s["brow"], s["mouth"]
        for S, k in (("L", 1), ("R", -1)):
            loc, n = self.hit_front(k * e["x"], fz + e["z"])
            R = frame_from_normal(n)
            M = Matrix.Translation(loc - n * 0.012 * hh) @ R.to_4x4() @ Matrix.Diagonal(
                (e["w"] * hh, 0.03 * hh, e["h"] * hh, 1))
            self.add(f"eye_{S}", sphere_bm(M), "eye", {"Head": 1.0, f"fx_eye_{S}": 1.0})
            if e["hl"]:
                c = loc + n * 0.016 * hh + R @ Vector((-k * e["w"] * 0.3 * hh, 0, e["h"] * 0.38 * hh))
                M = Matrix.Translation(c) @ R.to_4x4() @ Matrix.Diagonal((0.022 * hh, 0.008 * hh, 0.026 * hh, 1))
                self.add(f"eyehl_{S}", sphere_bm(M, 10, 6), "eye_hl", {"Head": 1.0, f"fx_eye_{S}": 1.0})
            if s["lashes"]:
                xo = k * (e["x"] + e["w"] * 0.95)
                pts = []
                for t in (0.0, 0.5, 1.0):
                    x = k * e["x"] + (xo - k * e["x"]) * (0.6 + 0.4 * t)
                    pl, pn = self.hit_front(x, fz + e["z"] + e["h"] * (0.75 + 0.35 * t))
                    pts.append(pl + pn * 0.01 * hh)
                bm = bmesh.new()
                sweep(bm, pts, [0.014 * hh, 0.011 * hh, 0.005 * hh], prof=8)
                self.add(f"lash_{S}", bm, "eye", {"Head": 1.0, f"fx_eye_{S}": 1.0})
            # まゆ
            pts = []
            for t in [i / 6 for i in range(7)]:
                x = k * (e["x"] - br["len"] * 0.45 + br["len"] * t)
                z = fz + e["z"] + br["z"] + br["arch"] * math.sin(math.pi * t) + br["tilt"] * (0.5 - t)
                pl, pn = self.hit_front(x, z)
                pts.append(pl + pn * br["t"] * 0.35 * hh)
            bm = bmesh.new()
            sweep(bm, pts, [br["t"] * hh * f for f in (0.7, 0.95, 1, 1, 0.95, 0.8, 0.5)], prof=8)
            self.add(f"brow_{S}", bm, "brow", {"Head": 1.0, f"fx_brow_{S}": 1.0})
            if s["blush"]:
                pl, pn = self.hit_front(k * (e["x"] + 0.06), fz + e["z"] - 0.13)
                M = Matrix.Translation(pl - pn * 0.004 * hh) @ frame_from_normal(pn).to_4x4() @ Matrix.Diagonal(
                    (0.07 * hh, 0.01 * hh, 0.035 * hh, 1))
                self.add(f"cheek_{S}", sphere_bm(M, 16, 8), "cheek", {"Head": 1.0})
        # 口
        pts = []
        for t in [i / 8 for i in range(9)]:
            u = t * 2 - 1
            pl, pn = self.hit_front(mo["w"] * u, fz + mo["z"] + mo["smile"] * u * u)
            pts.append(pl + pn * 0.004 * hh)
        bm = bmesh.new()
        sweep(bm, pts, [mo["t"] * hh * f for f in (0.5, 0.85, 1, 1, 1, 1, 1, 0.85, 0.5)], prof=8, ell=(0.6, 1.0))
        self.add("mouth", bm, "mouth", {"Head": 1.0, "fx_mouth": 1.0})
        if s["mustache"]:
            for k in (1, -1):
                pl, pn = self.hit_front(k * 0.055, fz + mo["z"] + 0.075)
                R = frame_from_normal(pn) @ Matrix.Rotation(-k * 0.25, 3, "Y")
                M = Matrix.Translation(pl) @ R.to_4x4() @ Matrix.Diagonal((0.075 * hh, 0.035 * hh, 0.032 * hh, 1))
                self.add(f"mustache_{S}{k}", sphere_bm(M, 16, 8), "brow", {"Head": 1.0})
        if s["glasses"]:
            self.glasses()

    def glasses(self):
        s, L, hh = self.s, self.L, self.hh
        e = s["eye"]
        fz = L["face_z"] + e["z"]
        r = max(e["w"], e["h"]) * 1.55 + 0.02
        y_front = min(self.hit_front(k * e["x"], fz)[0].y for k in (1, -1)) / hh - 0.05
        bm = bmesh.new()
        inner = {}
        for k in (1, -1):
            c = Vector((k * e["x"], y_front, fz))
            pts = [self.v(c.x + r * 1.1 * math.cos(a), c.y, c.z + r * 0.82 * math.sin(a))
                   for a in (2 * math.pi * i / 28 for i in range(28))]
            sweep(bm, pts, [0.012 * hh] * 28, closed=True, prof=6)
            inner[k] = c
            # つる：外側の縁から耳へ
            ear = self.hit_front(k * s["head"][0] * 0.9, fz)[0] / hh
            pts = [self.v(k * (e["x"] + r * 1.1), y_front, fz), self.v(k * (s["head"][0] + 0.02), y_front + 0.12, fz),
                   self.v(k * (s["head"][0] + 0.03), 0.05, fz - 0.02)]
            sweep(bm, pts, [0.01 * hh] * 3, prof=6)
            _ = ear
        pts = [self.v(e["x"] - r * 1.1, y_front, fz + 0.02), self.v(0, y_front - 0.01, fz + 0.035),
               self.v(-(e["x"] - r * 1.1), y_front, fz + 0.02)]
        sweep(bm, pts, [0.011 * hh] * 3, prof=6)
        self.add("glasses", bm, "glass", {"Head": 1.0})

    # 髪 ------------------------------------------------------------------------
    def hair(self):
        s, hh = self.s, self.hh
        B = self.B
        v = self.v
        hx, hy, hz = s["head"]
        c = Vector((0, 0.03, B + 0.55))
        m = Meta(f"{s['name']}_hairMB", 0.014 * hh)
        sz = lambda *a: [x * hh for x in a]  # noqa: E731
        style = s["hair"]
        ears = lambda r: [m.ball(v(k * hx * 1.02, 0.04, B + 0.43), r * hh, neg=True) for k in (1, -1)]  # noqa: E731
        if style == "short":
            m.ell(v(c.x, c.y + 0.03, c.z + 0.06), sz(hx + 0.045, hy + 0.05, hz + 0.0))
            m.ell(v(0, -0.12, B + 1.0), sz(0.30, 0.25, 0.10), Quaternion((1, 0, 0), -0.3))
            m.ell(v(0.1, -0.33, B + 0.86), sz(0.22, 0.12, 0.10), Quaternion((0, 1, 0), 0.4))
            m.ell(v(-0.12, -0.3, B + 0.9), sz(0.18, 0.12, 0.09), Quaternion((0, 1, 0), -0.3))
            m.ell(v(0, -0.47, B + 0.36), sz(0.42, 0.40, 0.48), neg=True)
            m.ell(v(0, 0.02, B - 0.12), sz(0.75, 0.75, 0.45), neg=True)
            ears(0.15)
        elif style == "bob":
            m.ell(v(c.x, c.y + 0.04, c.z + 0.04), sz(hx + 0.07, hy + 0.07, hz + 0.02))
            m.ell(v(0, 0.08, B + 0.33), sz(hx + 0.09, hy + 0.06, 0.3))
            m.ell(v(0, -0.34, B + 0.79), sz(0.40, 0.16, 0.17))
            m.ell(v(0, -0.50, B + 0.24), sz(0.33, 0.34, 0.45), neg=True)
            m.ell(v(0, 0.02, B - 0.30), sz(0.8, 0.8, 0.45), neg=True)
        elif style == "bald":
            m.ell(v(c.x, c.y + 0.05, c.z - 0.02), sz(hx + 0.04, hy + 0.04, hz - 0.02))
            m.ell(v(0, -0.08, B + 1.02), sz(0.52, 0.5, 0.33), neg=True)
            m.ell(v(0, -0.47, B + 0.36), sz(0.42, 0.40, 0.48), neg=True)
            m.ell(v(0, 0.02, B - 0.1), sz(0.75, 0.75, 0.45), neg=True)
            ears(0.13)
        elif style == "bun":
            m.ell(v(c.x, c.y + 0.03, c.z + 0.03), sz(hx + 0.04, hy + 0.045, hz + 0.01))
            m.ball(v(0, 0.36, B + 0.98), 0.19 * hh)
            m.ell(v(0, -0.47, B + 0.30), sz(0.40, 0.40, 0.55), neg=True)
            m.ell(v(0, 0.02, B - 0.08), sz(0.75, 0.75, 0.45), neg=True)
            ears(0.14)
        o = m.to_mesh(f"{s['name']}_hair")
        dec = o.modifiers.new("decimate", "DECIMATE")
        dec.ratio = 0.35
        apply_modifiers(o)
        o.data.shade_smooth()
        o.data.materials.append(self.mat("hair"))
        vg = o.vertex_groups.new(name="Head")
        vg.add(list(range(len(o.data.vertices))), 1.0, "REPLACE")
        self.parts.append(o)

    # 服の部品 --------------------------------------------------------------------
    def contour(self, center, axis, n=36, rmax=None):
        axis = axis.normalized()
        ref = Vector((1, 0, 0)) if abs(axis.x) < 0.9 else Vector((0, 1, 0))
        u = (ref - axis * ref.dot(axis)).normalized()
        w = axis.cross(u)
        out = []
        last = 0.2 * self.hh
        for i in range(n):
            a = 2 * math.pi * i / n
            d = u * math.cos(a) + w * math.sin(a)
            loc, *_ = self.bvh.ray_cast(center, d, 2 * self.hh)
            r = (loc - center).length if loc is not None else last
            if rmax is not None:
                r = min(r, rmax * self.hh)
            last = r
            out.append((d, r))
        return out

    def band(self, name, center_hh, axis, width, thick, mat, groups, off=0.0, rmax=None):
        hh = self.hh
        c = self.v(*center_hh)
        pts = [c + d * (r + (thick * 0.25 + off) * hh) for d, r in self.contour(c, Vector(axis), rmax=rmax)]
        bm = bmesh.new()
        sweep(bm, pts, [width * 0.5 * hh] * len(pts), closed=True, up=Vector(axis).normalized(), prof=10,
              ell=(thick / width, 1.0))
        return self.add(name, bm, mat, groups)

    def clothes(self):
        s, L, hh = self.s, self.L, self.hh
        wr, sh = L["wrist_x"], s["sh_x"]
        z = L["sh_z"]
        for S, k in (("Left", 1), ("Right", -1)):
            t = s["sleeve"]
            x = sh + (wr - sh) * min(t, 1.0) - (0.03 if t >= 1 else 0)
            bone = f"{S}ForeArm" if t >= 0.5 else f"{S}Arm"
            if s["cuffs"]:
                self.band(f"cuff_{S}", (k * x, 0.03, z), (1, 0, 0), 0.07, 0.035, "top", {bone: 1.0})
            if s["rolled"]:
                hem = s["foot"][2] + 0.1
                self.band(f"roll_{S}", (k * s["leg_x"], 0.03, hem), (0, 0, 1), 0.09, 0.04, "bottom", {f"{S}Leg": 1.0})
        if s["top_hem"] is not None and s["bottom"] != "skirt":
            self.band("hem", (0, 0.03, L["hips_z"] + s["top_hem"] + 0.02), (0, 0, 1), 0.08, 0.035, "top", {"Hips": 1.0})
        if s["collar"]:
            self.band("collar", (0, 0.04, L["neck_base"] + 0.06), (0, 0, 1), 0.07, 0.05, "inner", {"Spine2": 1.0},
                      rmax=s["neck_r"] * 1.6)
        if s["v_neck"]:
            self.band("collar", (0, 0.04, L["neck_base"] + 0.05), (0, 0, 1), 0.06, 0.04, "inner", {"Spine2": 1.0},
                      rmax=s["neck_r"] * 1.6)
            vn = s["v_neck"]
            vb = L["neck_base"] + vn["bottom"]
            for k in (1, -1):   # カーディガンの前の縁（色の境目のギザギザを隠す）
                pts = []
                for i in range(9):
                    t = i / 8
                    zz = L["neck_base"] - 0.02 + (vb - L["neck_base"] + 0.02) * t
                    pl, pn = self.hit_front(k * (vn["w"] * (1 - t) + 0.005), zz)
                    pts.append(pl + pn * 0.012 * hh)
                bm = bmesh.new()
                sweep(bm, pts, [0.03 * hh] * len(pts), prof=8, ell=(0.6, 1.0))
                self.add(f"lapel{k}", bm, "top", {"Spine2": 1.0})
        if s["buttons"]:
            vb = L["neck_base"] + s["v_neck"]["bottom"]
            lo = L["hips_z"] + s["top_hem"] + 0.12
            for i in range(s["buttons"]):
                zz = vb - 0.03 - (vb - 0.03 - lo) * i / max(s["buttons"] - 1, 1)
                pl, pn = self.hit_front(0.0, zz)
                M = Matrix.Translation(pl) @ frame_from_normal(pn).to_4x4() @ Matrix.Diagonal(
                    (0.03 * hh, 0.012 * hh, 0.03 * hh, 1))
                b = "Spine2" if zz > L["chest_z"] else "Spine1" if zz > L["waist_z"] else "Spine"
                self.add(f"button{i}", sphere_bm(M, 12, 6), "detail", {b: 1.0})
        if s["hood"]:
            M = Matrix.Translation(self.v(0, 0.33, z + 0.02)) @ Matrix.Rotation(-0.35, 4, "X") @ Matrix.Diagonal(
                (0.36 * hh, 0.17 * hh, 0.2 * hh, 1))
            self.add("hood", sphere_bm(M, 24, 12), "top", {"Spine2": 1.0})
            self.band("hoodrim", (0, 0.04, L["neck_base"] - 0.02), (0, 0.25, 1), 0.07, 0.06, "top", {"Spine2": 1.0},
                      off=0.01)
            for k in (1, -1):
                p0, n0 = self.hit_front(k * 0.08, L["neck_base"] - 0.08)
                p1, n1 = self.hit_front(k * 0.09, L["neck_base"] - 0.42)
                bm = bmesh.new()
                sweep(bm, [p0 + n0 * 0.02 * hh, p1 + n1 * 0.02 * hh], [0.014 * hh] * 2, prof=6)
                self.add(f"string{k}", bm, "inner", {"Spine2": 1.0})
        if s["bottom"] == "skirt":
            self.skirt()

    def skirt(self):
        s, L, hh = self.s, self.L, self.hh
        n = 40
        top = L["waist_z"] - 0.08
        widest = L["leg_z"] + 0.05
        hem = s["skirt_hem"] + L["knee_z"]
        c_top = self.contour(self.v(0, 0.03, top), Vector((0, 0, 1)), n)
        rs = [0.0] * n
        for zz in [widest + 0.03 * i for i in range(-2, 6)]:
            for i, (_, r) in enumerate(self.contour(self.v(0, 0.03, zz), Vector((0, 0, 1)), n)):
                rs[i] = max(rs[i], r)
        rows = 10
        bm = bmesh.new()
        grid = []
        for j in range(rows + 1):
            t = j / rows
            zz = top + (hem - top) * t
            row = []
            for i in range(n):
                d = c_top[i][0]
                if zz >= widest:
                    f = (top - zz) / (top - widest)
                    r = c_top[i][1] + (rs[i] - c_top[i][1]) * math.sin(f * math.pi / 2) + 0.012 * hh
                else:
                    f = (widest - zz) / (widest - hem)
                    r = (rs[i] + 0.012 * hh) * (1 + s["flare"] * f)
                p = self.v(0, 0.03, zz) + d * r
                row.append(bm.verts.new(p))
            grid.append(row)
        for j in range(rows):
            for i in range(n):
                bm.faces.new((grid[j][i], grid[j][(i + 1) % n], grid[j + 1][(i + 1) % n], grid[j + 1][i]))
        o = mesh_object(f"{s['name']}_skirt", bm, self.mat("bottom"))
        so = o.modifiers.new("solid", "SOLIDIFY")
        so.thickness = 0.025 * hh
        so.offset = 1.0
        apply_modifiers(o)
        o.data.shade_smooth()
        # 重み：腰から下へ、だんだん左右のももに移す（座ると前が太ももについていく）
        gh, gl, gr = (o.vertex_groups.new(name=n_) for n_ in ("Hips", "LeftUpLeg", "RightUpLeg"))
        for vtx in o.data.vertices:
            p = vtx.co / hh
            t = min(max((L["leg_z"] + 0.1 - p.z) / (L["leg_z"] + 0.1 - hem), 0.0), 1.0) ** 0.8
            side = 1 / (1 + math.exp(-p.x / 0.06))
            if t < 1:
                gh.add([vtx.index], 1 - t, "REPLACE")
            if t > 0:
                gl.add([vtx.index], t * side, "REPLACE")
                gr.add([vtx.index], t * (1 - side), "REPLACE")
        self.parts.append(o)

    # まとめ ----------------------------------------------------------------------
    def bind_and_join(self):
        arm, body = self.arm, self.body_obj
        bpy.ops.object.select_all(action="DESELECT")
        body.select_set(True)
        arm.select_set(True)
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.parent_set(type="ARMATURE_AUTO")
        empty = [vt.index for vt in body.data.vertices if not vt.groups]
        if empty:
            print(f"[chars] 重みのない頂点が {len(empty)} 個（{self.s['name']}）")
        bpy.ops.object.select_all(action="DESELECT")
        for o in self.parts:
            o.select_set(True)
        body.select_set(True)
        bpy.context.view_layer.objects.active = body
        bpy.ops.object.join()
        body.data.shade_smooth()

    def shape_keys(self):
        o = self.body_obj
        hh = self.hh
        groups = {vg.name: vg.index for vg in o.vertex_groups if vg.name.startswith("fx_")}
        members = {g: [] for g in groups}
        inv = {i: g for g, i in groups.items()}
        for vt in o.data.vertices:
            for ge in vt.groups:
                if ge.group in inv and ge.weight > 0.5:
                    members[inv[ge.group]].append(vt.index)
        V = [vt.co.copy() for vt in o.data.vertices]

        def centroid(g):
            ids = members[g]
            return sum((V[i] for i in ids), Vector()) / len(ids)

        o.shape_key_add(name="Basis", from_mix=False)

        def key(name, fn):
            sk = o.shape_key_add(name=name, from_mix=False)
            for g, ids in members.items():
                c = centroid(g)
                xs = [V[i].x for i in ids]
                w = (max(xs) - min(xs)) / 2 or 1e-6
                for i in ids:
                    p = fn(g, V[i].copy(), c, w)
                    if p is not None:
                        sk.data[i].co = p

        def blink(g, p, c, w):
            if g.startswith("fx_eye"):
                p.z = c.z - 0.25 * w + (p.z - c.z) * 0.12
                return p

        def smile(g, p, c, w):
            u = (p.x - c.x) / w
            if g == "fx_mouth":
                p.z += 0.05 * hh * u * u - 0.01 * hh
                p.x = c.x + (p.x - c.x) * 1.1
                return p
            if g.startswith("fx_eye"):
                p.z = c.z + (p.z - c.z) * 0.7
                return p

        mo = self.s["mouth"]
        mw = mo["w"] * hh

        def mouth_open(p, c, height, narrow=1.0):
            """口の線を、真ん中ほど上下に開いたレンズ形にする（両端は閉じたまま）。"""
            u = max(-1.0, min(1.0, (p.x - c.x) / mw))
            zc = c.z - mo["smile"] * hh / 3
            base = zc + mo["smile"] * hh * u * u
            thick = 1 - u * u
            k = (height * hh / 2) / (0.6 * mo["t"] * hh)
            p.z = zc - height * hh * 0.3 * thick + (p.z - base) * (1 + (k - 1) * thick)
            p.x = c.x + (p.x - c.x) * narrow
            return p

        def open_(g, p, c, w):
            if g == "fx_mouth":
                return mouth_open(p, c, 0.075, 0.85)

        def surprise(g, p, c, w):
            if g.startswith("fx_brow"):
                p.z += 0.06 * hh
                return p
            if g.startswith("fx_eye"):
                return c + (p - c) * 1.18
            if g == "fx_mouth":
                return mouth_open(p, c, 0.06, 0.45)

        def brow_tilt(g, p, c, w, amount):
            if g.startswith("fx_brow"):
                inner = 1 - (abs(p.x) - (abs(c.x) - w)) / (2 * w)    # 内側の端 = 1
                p.z += amount * hh * (inner - 0.3)
                return p

        def angry(g, p, c, w):
            if g.startswith("fx_brow"):
                return brow_tilt(g, p, c, w, -0.07)
            if g.startswith("fx_eye"):
                p.z = c.z + (p.z - c.z) * 0.8
                return p
            if g == "fx_mouth":
                u = (p.x - c.x) / w
                p.z -= 0.025 * hh * u * u
                return p

        def sad(g, p, c, w):
            if g.startswith("fx_brow"):
                return brow_tilt(g, p, c, w, 0.06)
            if g == "fx_mouth":
                u = (p.x - c.x) / w
                p.z -= 0.04 * hh * u * u - 0.01 * hh
                return p

        for name, fn in (("blink", blink), ("smile", smile), ("open", open_), ("surprise", surprise),
                         ("angry", angry), ("sad", sad)):
            key(name, fn)
        for g in list(groups):
            o.vertex_groups.remove(o.vertex_groups[g])

    def build(self):
        self.armature()
        self.body()
        self.paint()
        self.face()
        self.hair()
        self.clothes()
        self.bind_and_join()
        self.shape_keys()
        return self.arm, self.body_obj


def export(name: str, out_dir: Path) -> Path:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    s = spec_of(name)
    arm, body = Builder(s).build()
    bpy.ops.object.select_all(action="DESELECT")
    arm.select_set(True)
    body.select_set(True)
    bpy.context.view_layer.objects.active = arm
    path = out_dir / f"own_{name}.glb"
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True,
                              export_animations=False, export_morph=True, export_skins=True)
    print(f"[chars] {s['label']} → {path}（頂点 {len(body.data.vertices)}）")
    return path


# ---- 下見の絵 --------------------------------------------------------------------------

def preview(paths: list[Path], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    def scene_base(w, h):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        sc = bpy.context.scene
        sc.render.engine = "BLENDER_EEVEE"
        sc.eevee.taa_render_samples = 32
        sc.render.resolution_x, sc.render.resolution_y = w, h
        sc.view_settings.view_transform = "AgX"
        sc.view_settings.look = "AgX - Medium High Contrast"
        world = bpy.data.worlds.new("w")
        sc.world = world
        if world.node_tree is None:
            world.use_nodes = True
        world.node_tree.nodes["Background"].inputs["Color"].default_value = (*srgb("#C9CDD3"), 1)
        world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
        bpy.ops.mesh.primitive_plane_add(size=40)
        floor = bpy.context.active_object
        floor.data.materials.append(make_material("floor", "#D8D4CC", rough=0.9))
        for name, loc, energy, size in (("key", (-3, -5, 6), 700, 4), ("fill", (4, -4, 3), 250, 5),
                                        ("rim", (0, 5, 5), 500, 4)):
            ld = bpy.data.lights.new(name, "AREA")
            ld.energy, ld.size = energy, size
            lo = bpy.data.objects.new(name, ld)
            col().objects.link(lo)
            lo.location = loc
            lo.rotation_euler = (Vector((0, 0, 1)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        return sc

    def load(path, x, rot=0.0, keys=None):
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(path))
        new = [o for o in bpy.data.objects if o not in before]
        for o in new:
            if o.parent is None:
                o.location.x += x
                o.rotation_euler.z += rot
            if o.type == "MESH" and o.data.shape_keys:   # 読み込むと形状キーがすべて 1 になるので 0 に戻す
                for kb in o.data.shape_keys.key_blocks:
                    kb.value = 0.0
                for k, val in (keys or {}).items():
                    o.data.shape_keys.key_blocks[k].value = val
        return new

    def camera(loc, target, lens=50, ortho=None):
        cd = bpy.data.cameras.new("cam")
        cd.lens = lens
        if ortho:
            cd.type = "ORTHO"
            cd.ortho_scale = ortho
        cam = bpy.data.objects.new("cam", cd)
        col().objects.link(cam)
        cam.location = loc
        cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        bpy.context.scene.camera = cam

    def shot(fname):
        sc = bpy.context.scene
        sc.render.filepath = str(out_dir / fname)
        bpy.ops.render.render(write_still=True)
        print(f"[chars] preview → {sc.render.filepath}")

    xs = [(-1.5 + i) * 1.0 for i in range(len(paths))]
    scene_base(1800, 1000)
    for p, x in zip(paths, xs):
        load(p, x)
    camera((0, -7.2, 1.0), (0, 0, 0.85), lens=50)
    shot("lineup_front.png")

    scene_base(1800, 1000)
    for p, x in zip(paths, xs):
        load(p, x, rot=0.6)
    camera((1.2, -7.0, 1.6), (0, 0, 0.8), lens=50)
    shot("lineup_angle.png")

    exprs = [None, {"smile": 1}, {"open": 1}, {"surprise": 1}, {"angry": 1}, {"sad": 1}, {"blink": 1}]
    for p in paths:
        scene_base(2100, 420)
        for i, k in enumerate(exprs):
            load(p, (i - 3) * 0.6, keys=k)
        bpy.context.view_layer.update()
        zs = [o.matrix_world.translation.z for o in bpy.data.objects if o.type == "ARMATURE"]
        heads = [b for o in bpy.data.objects if o.type == "ARMATURE" for b in o.data.bones if b.name == "Head"]
        hz = max((o.matrix_world @ heads[0].head_local).z for o in bpy.data.objects if o.type == "ARMATURE") + 0.12
        _ = zs
        camera((0, -8, hz), (0, 0, hz), ortho=4.4)
        shot(f"faces_{p.stem}.png")


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="作る人形（カンマ区切り）。空ならすべて")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--preview", default="", help="並べた絵を書き出すフォルダ")
    a = ap.parse_args(argv)
    names = [n for n in a.only.split(",") if n] or list(SPECS)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    paths = [export(n, out) for n in names]
    if a.preview:
        preview(paths, Path(a.preview))


if __name__ == "__main__":
    main()
