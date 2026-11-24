"""3D の舞台の部品（Blender の中で使う）。物語ごとの scripts/blender/{id}.py から読み込む。

    sys.path.insert(0, str(Path(__file__).parent)); import kit

- シーンの準備（EEVEE・解像度・色）と引数（--timing / --out / --stills …）
- 材質（単色・木目）と基本図形（箱・球・円柱・空）
- 光、キーフレームの補間
- 人形（assets/3d/characters/*.glb）：読み込み・大きさ合わせ・座る／立つ／歩く・手足の行き先（IK）と手の向き・物を持つ・首と胴の向き
- Mixamo の動き（assets/3d/motions/mixamo/*.fbx。各自で落とす）を人形に移す：play / bake（D-027）
- 書き出し（下見のコマ / 全編）
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector

REPO = Path(__file__).resolve().parents[2]
CHARACTERS = REPO / "assets" / "3d" / "characters"
MOTIONS = REPO / "assets" / "3d" / "motions" / "mixamo"   # Mixamo の動き（各自で落とす。git に入れない）


# ---- 引数とシーン ---------------------------------------------------------------

def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--timing", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--stills", default="", help="この秒のコマだけ PNG で書き出す（カンマ区切り）。none で書き出さない")
    ap.add_argument("--scale", type=int, default=100, help="解像度の %（下見は 50）")
    ap.add_argument("--samples", type=int, default=16)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--height", type=int, default=1920)
    return ap.parse_args(argv)


class Timeline:
    """timing.json の文の時刻と、秒 → フレームの変換。"""

    def __init__(self, timing_path: str, fps: int):
        t = json.loads(Path(timing_path).read_text(encoding="utf-8"))
        self.S = {s["index"]: s for s in t["sentences"]}
        self.duration = float(t["duration"])
        self.fps = fps

    def F(self, t: float) -> int:
        return int(round(t * self.fps)) + 1


def setup_scene(args, duration: float, world_color=(0.012, 0.016, 0.035)):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    for engine in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    scene.eevee.taa_render_samples = args.samples
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.resolution_percentage = args.scale
    scene.render.fps = args.fps
    scene.frame_start = 1
    scene.frame_end = int(round(duration * args.fps)) + 1
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    world = bpy.data.worlds.new("World")
    scene.world = world
    if world.node_tree is None:
        world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (*world_color, 1)
    return scene


def col():
    return bpy.context.scene.collection


# ---- 補間 --------------------------------------------------------------------

def interp(kind: str) -> None:
    """これから打つキーの補間。-b では効かないことがあるので、点滅は make_constant でも直す。"""
    bpy.context.preferences.edit.keyframe_new_interpolation_type = kind


def fcurves_of(id_):
    ad = id_.animation_data
    if not ad or not ad.action:
        return []
    try:
        from bpy_extras.anim_utils import action_get_channelbag_for_slot
        bag = action_get_channelbag_for_slot(ad.action, ad.action_slot)
        return list(bag.fcurves) if bag else []
    except ImportError:
        return list(ad.action.fcurves)


def set_interp(id_, frames, kind: str, path: str | None = None) -> None:
    """id_ のキーのうち、frames のフレームにあるものの補間を kind にする（そのキーから次のキーまでの動き方）。"""
    fs = {int(f) for f in frames}
    for fc in fcurves_of(id_):
        if path and fc.data_path != path:
            continue
        for k in fc.keyframe_points:
            if int(round(k.co.x)) in fs:
                k.interpolation = kind


HOLD = 15   # 動き出す何コマ前まで止まっているか（0.5 秒）


def hold_before(id_, path: str, frame: int, gap: int = HOLD, kind: str = "BEZIER") -> None:
    """frame に新しいキーを打つ前に、frame - gap に「今の値」のキーを打つ（そこまでは止まっている）。
    キーの間が長いと、なめらかな補間で何秒もかけてずれていくのを防ぐ。"""
    f0 = frame - gap
    for fc in fcurves_of(id_):
        if fc.data_path != path:
            continue
        before = [k.co.x for k in fc.keyframe_points if k.co.x < frame - 0.5]
        if not before or max(before) >= f0:
            continue
        k = fc.keyframe_points.insert(f0, fc.evaluate(f0))
        k.interpolation = kind


def make_constant(id_) -> None:
    """id_ のキーをすべて「パッと切り替え」にする（Blender 5 のスロット付きアクション対応）。"""
    for fc in fcurves_of(id_):
        for k in fc.keyframe_points:
            k.interpolation = "CONSTANT"


# ---- 材質 --------------------------------------------------------------------

def material(name, color, rough=0.6, emission=None, strength=0.0):
    m = bpy.data.materials.new(name)
    if m.node_tree is None:
        m.use_nodes = True
    nodes = m.node_tree.nodes
    bsdf = nodes.get("Principled BSDF") or nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = rough
    if emission:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1)
        bsdf.inputs["Emission Strength"].default_value = strength
    return m


def emission_socket(m):
    return m.node_tree.nodes.get("Principled BSDF").inputs["Emission Strength"]


def wood(name, dark, light, stretch=(1.0, 16.0, 1.0)):
    """引き伸ばしたノイズで木目を作る。"""
    m = material(name, dark, rough=0.45)
    nt = m.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = stretch
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 3.0
    nz.inputs["Detail"].default_value = 8.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (*dark, 1)
    ramp.color_ramp.elements[1].position = 0.7
    ramp.color_ramp.elements[1].color = (*light, 1)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], nz.inputs["Vector"])
    nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    return m


# ---- 形 ----------------------------------------------------------------------

def _finish(o, name, mat, parent, loc, rot, smooth):
    o.name = name
    if mat:
        o.data.materials.append(mat)
    if smooth:
        try:
            bpy.ops.object.shade_smooth_by_angle()
        except (AttributeError, RuntimeError):
            bpy.ops.object.shade_smooth()
    o.parent = parent
    o.location = loc
    o.rotation_euler = rot
    return o


def box(name, size, loc, mat, parent=None, rot=(0, 0, 0), bevel=0.01):
    bpy.ops.mesh.primitive_cube_add(size=1)
    o = bpy.context.active_object
    o.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        b = o.modifiers.new("bevel", "BEVEL")
        b.width = bevel
        b.segments = 3
    return _finish(o, name, mat, parent, loc, rot, smooth=bool(bevel))


def ball(name, r, loc, mat, parent=None, scale=(1, 1, 1), rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=32, ring_count=16)
    o = bpy.context.active_object
    o.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.ops.object.shade_smooth()
    return _finish(o, name, mat, parent, loc, rot, smooth=False)


def rod(name, r, depth, loc, mat, parent=None, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=depth, vertices=32)
    o = bpy.context.active_object
    b = o.modifiers.new("bevel", "BEVEL")
    b.width = min(r * 0.4, 0.02)
    b.segments = 3
    return _finish(o, name, mat, parent, loc, rot, smooth=True)


def cone(name, r1, r2, depth, loc, mat):
    bpy.ops.mesh.primitive_cone_add(radius1=r1, radius2=r2, depth=depth, vertices=48)
    return _finish(bpy.context.active_object, name, mat, None, loc, (0, 0, 0), smooth=True)


def empty(name, loc=(0, 0, 0), parent=None, rot=(0, 0, 0)):
    o = bpy.data.objects.new(name, None)
    col().objects.link(o)
    o.parent = parent
    o.location = loc
    o.rotation_euler = rot
    o.empty_display_size = 0.1
    return o


def aim(obj, target):
    d = Vector(target) - obj.location
    obj.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def light(name, kind, loc, energy, color, size=0.1, target=None):
    data = bpy.data.lights.new(name, kind)
    data.energy = energy
    data.color = color
    data.shadow_soft_size = size
    if kind == "AREA":
        data.size = size
    o = bpy.data.objects.new(name, data)
    col().objects.link(o)
    o.location = loc
    if target:
        aim(o, target)
    return o


# ---- 家具 --------------------------------------------------------------------

def chair(name, loc, facing, mat):
    """座面の高さ 0.46。facing はラジアン（0 で +X を向く）。"""
    root = empty(f"{name}_root", loc, rot=(0, 0, facing))
    box(f"{name}_seat", (0.42, 0.42, 0.05), (-0.02, 0, 0.44), mat, parent=root, bevel=0.01)
    box(f"{name}_back", (0.04, 0.42, 0.5), (-0.22, 0, 0.72), mat, parent=root, bevel=0.01)
    for sx in (-1, 1):
        for sy in (-1, 1):
            rod(f"{name}_leg{sx}{sy}", 0.018, 0.44, (-0.02 + sx * 0.18, sy * 0.18, 0.22), mat, parent=root)
    return root


def table(name, loc, size, top_z, mat):
    sx, sy = size
    box(f"{name}_top", (sx, sy, 0.05), (loc[0], loc[1], top_z - 0.025), mat, bevel=0.01)
    for ix in (-1, 1):
        for iy in (-1, 1):
            rod(f"{name}_leg{ix}{iy}", 0.025, top_z - 0.025,
                (loc[0] + ix * (sx / 2 - 0.07), loc[1] + iy * (sy / 2 - 0.07), (top_z - 0.025) / 2), mat)


# ---- 人形 --------------------------------------------------------------------

# 骨の名前（リグごと）。L / R は人形から見た左右
RIGS = {
    "quaternius": {
        "hips": "Hips", "spine": "Chest", "neck": "Neck", "head": "Head",
        "upper_arm": "UpperArm.{s}", "lower_arm": "LowerArm.{s}", "hand": "Wrist.{s}",
        "upper_leg": "UpperLeg.{s}", "lower_leg": "LowerLeg.{s}", "foot": "Foot.{s}",
        "finger": "Index1.{s}", "thumb": "Thumb2.{s}",
        "foot_detached": True, "side": {"L": "L", "R": "R"},
        # IK の pole_angle（ひじ・ひざが正しい向きに曲がる値。2026-11-24 に下見で確かめた）
        # 腕は手のひらを下にしたとき手首がねじれない値（左腕を前に伸ばして確かめた）
        "poles": {"leg": {"L": math.pi, "R": 0.0}, "arm": {"L": math.pi, "R": 0.0}},
        # Mixamo の骨 → この人形の骨（動きを移すとき）。Quaternius の Body が Mixamo の Hips にあたる
        "mixamo_map": "quaternius",
    },
    "mixamo": {
        "hips": "Hips", "spine": "Spine2", "neck": "Neck", "head": "Head",
        "upper_arm": "{s}Arm", "lower_arm": "{s}ForeArm", "hand": "{s}Hand",
        "upper_leg": "{s}UpLeg", "lower_leg": "{s}Leg", "foot": "{s}Foot",
        "finger": "{s}HandIndex1", "thumb": "{s}HandThumb2",
        "foot_detached": False, "side": {"L": "Left", "R": "Right"},
        # 腕は -π/2 でひじが後ろ下へ曲がる（+π/2 だと前に出て逆に曲がって見えた。2026-11-25 に数値で確かめた）
        "poles": {"leg": {"L": 1.5708, "R": 1.5708}, "arm": {"L": -1.5708, "R": -1.5708}},
        "mixamo_map": "same",
    },
}


def _mixamo_map(kind: str, target_bones) -> dict:
    """Mixamo の骨の名前（mixamorig: を除いたもの）→ 人形の骨の名前。"""
    if kind == "same":
        return {n: n for n in target_bones}
    m = {"Hips": "Body", "Spine": "Abdomen", "Spine1": "Torso", "Spine2": "Chest", "Neck": "Neck", "Head": "Head"}
    for S, s in (("Left", "L"), ("Right", "R")):
        m.update({f"{S}Shoulder": f"Shoulder.{s}", f"{S}Arm": f"UpperArm.{s}", f"{S}ForeArm": f"LowerArm.{s}",
                  f"{S}Hand": f"Wrist.{s}", f"{S}UpLeg": f"UpperLeg.{s}", f"{S}Leg": f"LowerLeg.{s}"})
        for finger in ("Thumb", "Index", "Middle", "Ring", "Pinky"):
            for i in (1, 2, 3):
                m[f"{S}Hand{finger}{i}"] = f"{finger}{i}.{s}"
    return {k: v for k, v in m.items() if v in target_bones}


# ---- Mixamo の動き ---------------------------------------------------------------

_CLIPS: dict = {}


def load_clip(name: str) -> dict:
    """assets/3d/motions/mixamo/{name}.fbx（人形なし・30fps）を読み、コマごとの骨の向きを取り出す。
    向きは「人形の向き基準」の空間（前が -Y、上が +Z。Mixamo の Y Bot はもとからこの向き）で持つ。
    読み込んだ骨組みは、取り出したら消す。"""
    if name in _CLIPS:
        return _CLIPS[name]
    path = MOTIONS / f"{name}.fbx"
    if not path.exists():
        raise FileNotFoundError(f"Mixamo の動きがありません: {path}（mixamo.com から FBX・人形なしで落として置く）")
    before = {o.name for o in bpy.data.objects}
    bpy.ops.import_scene.fbx(filepath=str(path))
    objs = _new_objects(before)
    src = next(o for o in objs if o.type == "ARMATURE")
    act = src.animation_data.action
    fcs = {(fc.data_path, fc.array_index): fc for fc in fcurves_of(src)}
    bones = sorted(src.data.bones, key=lambda b: len(b.parent_recursive))
    W = src.matrix_world.copy()
    f0, f1 = (int(round(v)) for v in act.frame_range)

    def chan(b, prop, n, default):
        p = f'pose.bones["{b.name}"].{prop}'
        return [fcs[(p, i)].evaluate(f) if (p, i) in fcs else default[i] for i in range(n)]

    frames = []
    for f in range(f0, f1 + 1):
        M, out = {}, {}
        for b in bones:
            loc = Vector(chan(b, "location", 3, (0, 0, 0)))
            if src.pose.bones[b.name].rotation_mode == "QUATERNION":
                rot = Quaternion(chan(b, "rotation_quaternion", 4, (1, 0, 0, 0))).normalized().to_matrix()
            else:
                from mathutils import Euler
                rot = Euler(chan(b, "rotation_euler", 3, (0, 0, 0))).to_matrix()
            basis = Matrix.Translation(loc) @ rot.to_4x4()
            rel = (b.parent.matrix_local.inverted() @ b.matrix_local) if b.parent else b.matrix_local
            M[b.name] = (M[b.parent.name] @ rel if b.parent else rel) @ basis
            w = W @ M[b.name]
            out[b.name.split(":")[-1]] = (w.to_3x3().normalized().to_quaternion(), w.translation.copy())
        frames.append(out)
    rest = {}
    for b in bones:
        w = W @ b.matrix_local
        rest[b.name.split(":")[-1]] = (w.to_3x3().normalized().to_quaternion(), w.translation.copy())
    for o in objs:
        bpy.data.objects.remove(o, do_unlink=True)
    _CLIPS[name] = {"frames": frames, "rest": rest}
    return _CLIPS[name]


def _smooth(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def _new_objects(before):
    return [o for o in bpy.data.objects if o.name not in before]


class Character:
    """glb の人形。読み込んで、身長を合わせ、足元を原点に置く。前は -Y（glTF の +Z）。

    動かし方は「行き先」で決める：手・足の行き先の empty を IK で追わせ、胴・首・頭は回す。
    """

    def __init__(self, name: str, file: str, rig: str, height: float):
        self.name = name
        self.rig = RIGS[rig]
        before = {o.name for o in bpy.data.objects}
        bpy.ops.import_scene.gltf(filepath=str(CHARACTERS / file))
        objs = _new_objects(before)
        for o in objs:   # 書き出し用の補助の球（Icosphere）が入っているので消す
            if o.type == "MESH" and o.name.startswith("Icosphere"):
                bpy.data.objects.remove(o, do_unlink=True)
        objs = _new_objects(before)
        self.arm = next(o for o in objs if o.type == "ARMATURE")
        self.meshes = [o for o in objs if o.type == "MESH"]
        if self.arm.animation_data:
            self.arm.animation_data.action = None
        for pb in self.arm.pose.bones:
            pb.rotation_mode = "QUATERNION"
            pb.rotation_quaternion = (1, 0, 0, 0)
            pb.location = (0, 0, 0)
        self._fix_tails()
        self.root = empty(f"{name}_root")
        for o in objs:
            if o.parent is None and o != self.root:
                o.parent = self.root
        bpy.context.view_layer.update()
        # 前の向きを足の骨（かかと → つま先）から求め、-Y を向くように回す
        fwd = Vector((0, 0, 0))
        for side in ("L", "R"):
            pb = self.pb("foot", side)
            d = self.arm.matrix_world.to_3x3() @ (pb.tail - pb.head)
            fwd += Vector((d.x, d.y, 0))
        if fwd.length > 1e-6:
            ang = math.atan2(fwd.y, fwd.x) - math.atan2(-1, 0)
            self.root.rotation_euler = (0, 0, -ang)
            bpy.context.view_layer.update()
        lo, hi = self._bounds()
        s = height / (hi.z - lo.z)
        self.root.scale = (s, s, s)
        bpy.context.view_layer.update()
        lo, hi = self._bounds()
        self.root.location = (-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z)
        bpy.context.view_layer.update()
        # 位置合わせが済んだら、外側にもう1段 empty をかぶせて、置き場所と向きを決める
        self.place = empty(f"{name}_place")
        self.root.parent = self.place
        self.targets = {}
        self.free_arms = False     # True：腕は Mixamo の動きに任せ、物にふれるときだけ IK（seat(arms="clip")）
        self.plays = None          # Mixamo の動きの予定（play）。None のあいだは使わない
        self.offsets = {}          # turn の記録（動きを使うときは bake で重ねる）

    def _fix_tails(self):
        """腕と脚の骨の先端を次の関節まで伸ばす（IK は骨の先端を行き先に合わせるため）。
        Quaternius のリグは骨が短い切れ端なので、このままだと IK がひじ・ひざを手先と思う。
        休みの姿勢（edit bone）を変えても、メッシュは休みの姿勢では動かない。"""
        chains = []
        for side in ("L", "R"):
            chains += [(self.bone("upper_arm", side), self.bone("lower_arm", side)),
                       (self.bone("lower_arm", side), self.bone("hand", side)),
                       (self.bone("hand", side), self.bone("finger", side)),
                       (self.bone("upper_leg", side), self.bone("lower_leg", side)),
                       (self.bone("lower_leg", side), self.bone("foot", side))]
        if bpy.context.object and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        bpy.context.view_layer.objects.active = self.arm
        self.arm.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        eb = self.arm.data.edit_bones
        for a, b in chains:
            if (eb[b].head - eb[a].head).length > 1e-6:
                eb[a].tail = eb[b].head.copy()
        bpy.ops.object.mode_set(mode="OBJECT")
        self.arm.select_set(False)

    def _bounds(self):
        dg = bpy.context.evaluated_depsgraph_get()
        pts = []
        for o in self.meshes:
            ev = o.evaluated_get(dg)
            pts += [ev.matrix_world @ Vector(c) for c in ev.bound_box]
        lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        return lo, hi

    def bone(self, key: str, side: str | None = None) -> str:
        n = self.rig[key]
        return n.format(s=self.rig["side"][side]) if side else n

    def pb(self, key, side=None):
        return self.arm.pose.bones[self.bone(key, side)]

    def bone_world(self, key, side=None, tail=False) -> Vector:
        pb = self.pb(key, side)
        return self.arm.matrix_world @ (pb.tail if tail else pb.head)

    # 置き場所 --------------------------------------------------------------
    def put(self, loc, facing: float):
        """loc に置き、facing（ラジアン、0 で +X）を向く。"""
        self.place.location = loc
        # 人形の前は -Y。+X を向かせるには +90° 回す
        self.place.rotation_euler = (0, 0, facing + math.pi / 2)
        bpy.context.view_layer.update()

    def local(self, v) -> Vector:
        """人形の向きを基準にした座標（x = 前、y = 左、z = 上。原点は置き場所）を世界の座標に。"""
        m = self.place.matrix_world
        fwd = m.to_3x3() @ Vector((0, -1, 0))
        left = m.to_3x3() @ Vector((1, 0, 0))   # 前が -Y のとき、人形の左は +X
        up = Vector((0, 0, 1))
        return m.translation + fwd * v[0] + left * v[1] + up * v[2]

    @staticmethod
    def _obj(v) -> Vector:
        """向き基準の座標（前・左・上）→ 置き場所（place）の中の座標。place の中では前が -Y、左が +X。"""
        return Vector((v[1], -v[0], v[2]))

    def place_matrix(self, frame: int | None = None) -> Matrix:
        """そのフレームでの置き場所の行列（人形が歩くときは、フレームを進めて読む）。"""
        if frame is not None and bpy.context.scene.frame_current != frame:
            bpy.context.scene.frame_set(frame)
        return self.place.matrix_world.copy()

    def to_local(self, world, frame: int | None = None) -> Vector:
        """世界の座標 → そのフレームでの向き基準の座標（前・左・上）。"""
        o = self.place_matrix(frame).inverted() @ Vector(world)
        return Vector((-o.y, o.x, o.z))

    # IK --------------------------------------------------------------------
    def ik(self, limb: str, side: str, target_local, pole_local, pole_angle: float = 0.0):
        """手（limb='arm'）か足（'leg'）を、target の empty に届かせる。pole はひじ・ひざの向き。
        行き先と pole は置き場所（place）の子にする。人形が歩くと、いっしょについてくる。"""
        lower = "lower_arm" if limb == "arm" else "lower_leg"
        t = empty(f"{self.name}_{limb}_{side}_target", self._obj(target_local), parent=self.place)
        p = empty(f"{self.name}_{limb}_{side}_pole", self._obj(pole_local), parent=self.place)
        c = self.pb(lower, side).constraints.new("IK")
        c.target = t
        c.pole_target = p
        c.pole_angle = pole_angle
        c.chain_count = 2
        if limb == "leg" and self.rig["foot_detached"]:
            # 足の骨が脚とつながっていないリグ：足を行き先に置く
            f = self.pb("foot", side).constraints.new("COPY_LOCATION")
            f.target = t
        self.targets[(limb, side)] = t
        self.targets[(limb, side, "pole")] = p
        self.targets[(limb, side, "con")] = c
        return t

    def move(self, limb: str, side: str, t_frame: int, target_local=None, world=None, kind="BEZIER",
             hold=True):
        """手・足の行き先を動かしてキーを打つ（local は人形の向き基準、world は世界の座標）。"""
        e = self.targets[(limb, side)]
        loc = Vector(target_local) if target_local is not None else self.to_local(world, t_frame)
        if hold:
            hold_before(e, "location", t_frame, kind=kind)
        e.location = self._obj(loc)
        e.keyframe_insert("location", frame=t_frame)
        set_interp(e, [t_frame], kind)

    def hand_aim(self, side: str):
        """手の向きを決める empty（place の子）。手の骨は COPY_ROTATION でこの empty の向きをまねる。
        向きは orient / touch で決める。"""
        a = empty(f"{self.name}_hand_{side}_aim", parent=self.place)
        a.rotation_mode = "QUATERNION"
        c = self.pb("hand", side).constraints.new("COPY_ROTATION")
        c.target = a
        # 手の骨のローカルで、親指がどちらにあるか（骨の向き Y に直交させる）
        hb = self.pb("hand", side).bone
        th = self.pb("thumb", side).bone
        v = hb.matrix_local.to_3x3().inverted() @ (th.head_local - hb.head_local)
        v.y = 0.0
        self.targets[("aim", side)] = (a, c, v.normalized())
        return a

    def orient(self, side: str, frame: int, fingers, thumb, kind="BEZIER"):
        """手の向きを決めてキーを打つ。fingers（指先の向き）と thumb（親指の向き）は向き基準（前・左・上）。
        例：手のひらを下 = 指先は前、親指は体の内側。体の横に下げる = 指先は下、親指は前。"""
        a, _, thumb_local = self.targets[("aim", side)]
        y = self._obj(fingers).normalized()
        t = self._obj(thumb)
        t = (t - y * t.dot(y)).normalized()
        bone = Matrix((Vector((0, 1, 0)), thumb_local, Vector((0, 1, 0)).cross(thumb_local))).transposed()
        want = Matrix((y, t, y.cross(t))).transposed()
        hold_before(a, "rotation_quaternion", frame, kind=kind)
        a.rotation_quaternion = (want @ bone.inverted()).to_quaternion()
        a.keyframe_insert("rotation_quaternion", frame=frame)
        set_interp(a, [frame], kind)

    def touch(self, side: str, frame: int, wrist_world=None, fingers_world=None, on: bool = True):
        """手を物にのせる（on）／ひざに戻す（off）。手首の位置と、指先を向ける先を世界の座標で渡す。
        どちらも手のひらは下（親指は体の内側）。ひざでは、指先を前へ少し下げて太ももにそわせる。"""
        inward = Vector((0, -1, 0)) if side == "L" else Vector((0, 1, 0))
        if on:
            w = self.to_local(wrist_world, frame)
            fingers = self.to_local(fingers_world, frame) - w
            self.move("arm", side, frame, target_local=w)
        else:
            fingers = Vector((0.12, 0.0, -0.03))
            self.move("arm", side, frame, target_local=lap(self, side))
        self.orient(side, frame, fingers, inward)
        if self.free_arms:   # 腕が動きに任されているときは、ふれるあいだだけ IK と手の向きを効かせる
            for c in (self.targets[("arm", side, "con")], self.targets[("aim", side)][1]):
                c.influence = 1.0 if on else 0.0
                c.keyframe_insert("influence", frame=frame)

    def reach(self, side: str, frame: int, world=None, local=None, fingers=(1, 0, 0), thumb=(0, 0, 1),
              kind="BEZIER"):
        """手を世界の座標（または向き基準の座標）へ伸ばす。手の向きは fingers / thumb（向き基準）。"""
        loc = Vector(local) if local is not None else self.to_local(world, frame)
        self.move("arm", side, frame, target_local=loc, kind=kind)
        self.orient(side, frame, Vector(fingers), Vector(thumb), kind=kind)

    def hang(self, side: str, frame: int):
        """手を体の横に下げる（立っているとき）。"""
        self.reach(side, frame, local=hang_local(self, side), fingers=(0.15, 0, -1), thumb=(1, 0, 0))

    def show(self, frame: int, on: bool):
        """そのフレームから人形を見せる／隠す（出番の前後）。"""
        for o in self.meshes:
            show(o, frame, on)

    def jump(self, frame: int, xy=None, facing: float | None = None):
        """そのフレームで、別の場所・向きにぱっと移す（場面の切り替え）。手足の行き先もついてくる。"""
        self.place_matrix(frame - 1)
        self.place.keyframe_insert("location", frame=frame - 1)
        self.place.keyframe_insert("rotation_euler", frame=frame - 1)
        set_interp(self.place, [frame - 1], "CONSTANT")
        if xy is not None:
            self.place.location.x, self.place.location.y = xy
        if facing is not None:
            self.place.rotation_euler.z = facing + math.pi / 2
        self.place.keyframe_insert("location", frame=frame)
        self.place.keyframe_insert("rotation_euler", frame=frame)

    def face(self, frame: int, facing: float, kind="BEZIER"):
        """向き（ラジアン、0 で +X）を変えてキーを打つ。今の向きから近いほうへ回る。"""
        cur = self.place.rotation_euler.z
        want = facing + math.pi / 2
        want = cur + (want - cur + math.pi) % (2 * math.pi) - math.pi
        hold_before(self.place, "rotation_euler", frame, kind=kind)
        self.place.rotation_euler.z = want
        self.place.keyframe_insert("rotation_euler", index=2, frame=frame)
        set_interp(self.place, [frame], kind, path="rotation_euler")

    def hold(self, obj, side: str, offset=(0.0, 0.0, 0.0)):
        """物を手に持たせる（手の骨の子にする）。物は「握る軸」を +Z にして、握る所を原点に作っておく。
        握る軸は親指の向き（こぶしを縦にしたとき上）。offset は握る所からのずれ（m、骨の向き基準）。"""
        pb = self.pb("hand", side)
        _, _, thumb_local = self.targets[("aim", side)]
        bpy.context.view_layer.update()
        scale = (self.arm.matrix_world @ pb.bone.matrix_local).to_scale()[0]
        yb = Vector((0, 1, 0))
        rot = Matrix((yb.cross(thumb_local), yb, thumb_local)).transposed()   # 物の X, Y, Z → 骨の中
        grip = Vector((0, -pb.bone.length * 0.45, 0)) + Vector(offset) / scale
        obj.parent = self.arm
        obj.parent_type = "BONE"
        obj.parent_bone = pb.name
        obj.matrix_parent_inverse = Matrix.Identity(4)
        obj.matrix_basis = Matrix.Translation(grip) @ rot.to_4x4() @ Matrix.Scale(1 / scale, 4)
        return obj

    # 回す ------------------------------------------------------------------
    def turn(self, key: str, frame: int, pitch=0.0, yaw=0.0, roll=0.0):
        """胴・首・頭を、人形の向き基準で回してキーを打つ。
        pitch > 0 で前にかがむ、yaw > 0 で左を向く、roll > 0 で右に首をかしげる。
        Mixamo の動きを使うとき（play）は、ここでは記録だけして、bake で動きの上に重ねる。"""
        if self.plays is not None:
            self.offsets.setdefault(key, []).append((frame, pitch, yaw, roll))
            return
        pb = self.pb(key)
        m = self.place.matrix_world.to_3x3()
        fwd = (m @ Vector((0, -1, 0))).normalized()
        left = (m @ Vector((1, 0, 0))).normalized()
        # 左向きの軸で + に回すと上が前へ倒れる（右手の法則）
        q = (Quaternion(left, pitch) @ Quaternion(Vector((0, 0, 1)), yaw) @ Quaternion(fwd, roll))
        # 世界の回転を骨のローカルに直す（親は休みの姿勢として近似）
        rest = (self.arm.matrix_world @ pb.bone.matrix_local).to_3x3().normalized()
        local = rest.inverted() @ q.to_matrix() @ rest
        hold_before(self.arm, f'pose.bones["{pb.name}"].rotation_quaternion', frame)
        pb.rotation_quaternion = local.to_quaternion()
        interp("BEZIER")
        pb.keyframe_insert("rotation_quaternion", frame=frame)

    # Mixamo の動き -------------------------------------------------------
    def play(self, name: str, f0: int, f1: int, blend: int = 8, loop: bool = True, speed: float = 1.0,
             move: float = 1.0, amount: float = 1.0):
        """f0〜f1 のコマで Mixamo の動き name を流す。あとから足したものほど上に重なり、
        出入りの blend コマでなめらかに切り替わる。最初に足すもの（ふだんの姿勢）は全体に流す。
        loop=False なら1回だけ流して、終わったら最後の姿勢のまま。
        move は腰の移動の大きさ（立ち上がって前に出る動きを、机にぶつからないよう小さくするとき）。
        amount は動きの強さ（0〜1。下の姿勢とのあいだを取って、大げさな動きを控えめにする）。"""
        if self.plays is None:
            self.plays = []
        load_clip(name)
        self.plays.append({"name": name, "f0": f0, "f1": f1, "blend": blend, "loop": loop, "speed": speed,
                           "move": move, "amount": amount})

    def _clip_pose(self, f: int):
        """コマ f の、重ねたあとの骨の回り方（Mixamo の名前 → 休みの姿勢からの回転）と、腰の動いた量。"""
        rot, move = {}, Vector((0, 0, 0))
        for i, p in enumerate(self.plays):
            if not (p["f0"] <= f <= p["f1"]):
                continue
            clip = _CLIPS[p["name"]]
            n = len(clip["frames"])
            sf = int((f - p["f0"]) * p["speed"])
            sf = sf % n if p["loop"] else min(sf, n - 1)
            fr = clip["frames"][sf]
            bl = max(p["blend"], 1)
            w = 1.0 if i == 0 else _smooth(min((f - p["f0"]) / bl, (p["f1"] - f) / bl)) * p["amount"]
            d = (fr["Hips"][1] - clip["frames"][0]["Hips"][1]) * p["move"]
            rest = clip["rest"]
            for b, (q, _) in fr.items():
                dq = q @ rest[b][0].inverted()          # 休みの姿勢からの回り方（世界の向き）
                rot[b] = dq if (b not in rot or w >= 1) else rot[b].slerp(dq, w)
            move = move.lerp(d, w) if i else d
        return rot, move

    def _offset(self, key: str, f: int) -> Quaternion:
        """turn で記録した向き（コマのあいだはなめらかにつなぐ）。人形の向き基準の回転。"""
        keys = sorted(self.offsets[key])
        v = keys[-1][1:]
        if f <= keys[0][0]:
            v = keys[0][1:]
        else:
            for a, b in zip(keys, keys[1:]):
                if a[0] <= f <= b[0]:
                    t = _smooth((f - a[0]) / max(b[0] - a[0], 1))
                    v = [x + (y - x) * t for x, y in zip(a[1:], b[1:])]
                    break
        pitch, yaw, roll = v
        return Quaternion((1, 0, 0), pitch) @ Quaternion((0, 0, 1), yaw) @ Quaternion((0, -1, 0), roll)

    def bake(self, f_end: int):
        """play した動きと turn の向きを重ねて、1コマずつ骨にキーを打つ（書き出しの前に1回呼ぶ）。
        動きは「人形の向き基準」の空間で移す：Mixamo の骨が休みの姿勢から回った分だけ、
        人形の骨も（休みの姿勢の骨の向きを Mixamo にそろえてから）回す。脚は IK のまま（足は床から動かない）。"""
        if not self.plays:
            return
        bpy.context.view_layer.update()
        bones = self.arm.data.bones
        some = _CLIPS[self.plays[0]["name"]]["rest"]
        mp = {k: v for k, v in _mixamo_map(self.rig["mixamo_map"], set(bones.keys())).items() if k in some}
        inv = {v: k for k, v in mp.items()}
        K = self.place.matrix_world.inverted() @ self.arm.matrix_world      # 骨組みの空間 → 人形の向き基準
        Kq = K.to_3x3().normalized().to_quaternion()
        Kinv3 = K.inverted().to_3x3()
        R0 = {b.name: b.matrix_local.to_3x3().normalized().to_quaternion() for b in bones}
        pre = {}
        for b, src_name in inv.items():   # 人形の休みの姿勢を、骨の向きだけ Mixamo の休みの姿勢にそろえる
            t0 = Kq @ R0[b]
            y_t = t0 @ Vector((0, 1, 0))
            y_s = some[src_name][0] @ Vector((0, 1, 0))
            pre[b] = y_t.rotation_difference(y_s) @ t0
        order = sorted(bones, key=lambda b: len(b.parent_recursive))
        hips_t = mp["Hips"]
        scale = (K @ bones[hips_t].matrix_local).translation.z / some["Hips"][1].z
        affected = {}
        for key in self.offsets:
            top = bones[self.bone(key)]
            for b in [top] + list(top.children_recursive):
                affected.setdefault(b.name, []).append(key)
        keys_rot = {b.name: [] for b in order if b.name in inv}
        keys_loc = []
        for f in range(1, f_end + 1):
            rot, move = self._clip_pose(f)
            offs = {k: self._offset(k, f) for k in self.offsets}
            Rarm = {}
            for b in order:
                if b.name in inv and inv[b.name] in rot:
                    tc = rot[inv[b.name]] @ pre[b.name]
                    for k in reversed(affected.get(b.name, [])):
                        tc = offs[k] @ tc
                    Rarm[b.name] = Kq.inverted() @ tc
                elif b.parent:
                    Rarm[b.name] = Rarm[b.parent.name] @ R0[b.parent.name].inverted() @ R0[b.name]
                else:
                    Rarm[b.name] = R0[b.name]
                if b.name in keys_rot:
                    if b.parent:
                        basis = R0[b.name].inverted() @ R0[b.parent.name] @ Rarm[b.parent.name].inverted() @ Rarm[b.name]
                    else:
                        basis = R0[b.name].inverted() @ Rarm[b.name]
                    if keys_rot[b.name] and keys_rot[b.name][-1].dot(basis) < 0:
                        basis.negate()
                    keys_rot[b.name].append(basis)
            keys_loc.append(R0[hips_t].inverted() @ (Kinv3 @ (move * scale)))
        self._write_keys(keys_rot, hips_t, keys_loc)

    def _write_keys(self, keys_rot: dict, hips: str, keys_loc: list):
        """1コマずつのキーを、F カーブにまとめて書く（keyframe_insert を何万回も呼ぶと遅いので）。"""
        for name in list(keys_rot) + [hips]:
            pb = self.arm.pose.bones[name]
            pb.keyframe_insert("rotation_quaternion", frame=1)
            pb.keyframe_insert("location", frame=1)
        fcs = {(fc.data_path, fc.array_index): fc for fc in fcurves_of(self.arm)}

        def fill(path, idx, values):
            fc = fcs[(path, idx)]
            kp = fc.keyframe_points
            kp.clear()
            kp.add(len(values))
            co = []
            for i, v in enumerate(values):
                co += [i + 1, v]
            kp.foreach_set("co", co)
            fc.update()

        for name, qs in keys_rot.items():
            for i in range(4):
                fill(f'pose.bones["{name}"].rotation_quaternion', i, [q[i] for q in qs])
        for i in range(3):
            fill(f'pose.bones["{hips}"].location', i, [v[i] for v in keys_loc])

    def tint_texture(self, hue_lo: float, hue_hi: float, min_sat: float, color, strength=1.0):
        """画像で色を塗っている材質の、色相が hue_lo〜hue_hi（0〜1）で彩度 min_sat 以上の部分を color にする。
        金髪を黒髪にするときなど（肌・服の色相とぶつからない範囲で使う）。"""
        for o in self.meshes:
            for m in o.data.materials:
                if not m or not m.node_tree:
                    continue
                nt = m.node_tree
                bsdf = nt.nodes.get("Principled BSDF")
                link = next((l for l in nt.links if l.to_socket == bsdf.inputs["Base Color"]), None)
                if not link:
                    continue
                src = link.from_socket
                sep = nt.nodes.new("ShaderNodeSeparateColor")
                sep.mode = "HSV"
                nt.links.new(src, sep.inputs["Color"])

                def node_math(op, a, b):
                    n = nt.nodes.new("ShaderNodeMath")
                    n.operation = op
                    for i, v in enumerate((a, b)):
                        if isinstance(v, (int, float)):
                            n.inputs[i].default_value = v
                        else:
                            nt.links.new(v, n.inputs[i])
                    return n.outputs[0]

                h, s = sep.outputs[0], sep.outputs[1]
                mask = node_math("MULTIPLY", node_math("GREATER_THAN", h, hue_lo), node_math("LESS_THAN", h, hue_hi))
                mask = node_math("MULTIPLY", mask, node_math("GREATER_THAN", s, min_sat))
                mask = node_math("MULTIPLY", mask, strength)
                mix = nt.nodes.new("ShaderNodeMix")
                mix.data_type = "RGBA"
                nt.links.new(mask, mix.inputs["Factor"])
                nt.links.new(src, mix.inputs["A"])
                mix.inputs["B"].default_value = (*color, 1)
                nt.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])

    def recolor(self, material_name: str, color):
        """材質の色を変える（単色の材質だけ）。"""
        for o in self.meshes:
            for m in o.data.materials:
                if m and m.name.split(".")[0] == material_name:
                    bsdf = m.node_tree.nodes.get("Principled BSDF")
                    bsdf.inputs["Base Color"].default_value = (*color, 1)


def seat(char: Character, loc, facing: float, seat_h=0.46, leg_pole=None, arm_pole=None, arms="ik"):
    """椅子に座らせる：体を下げ、足をひざの真下の床に、手をひざの上に置く。
    行き先の座標は人形の向き基準（x = 前、y = 左）。置き場所の原点は下げた分だけ床より下にある。
    arms="clip" なら、腕は Mixamo の動き（play）に任せ、物にふれるとき（touch）だけ IK を効かせる。"""
    char.free_arms = arms == "clip"
    if char.free_arms and char.plays is None:
        char.plays = []
    char.put(loc, facing)
    hip = char.bone_world("upper_leg", "L")
    knee = char.bone_world("lower_leg", "L")
    ankle = char.bone_world("lower_leg", "L", tail=True)
    thigh = (knee - hip).length
    half = abs((hip - char.bone_world("upper_leg", "R")).length) / 2
    drop = hip.z - (seat_h + 0.06)
    char.place.location.z -= drop
    bpy.context.view_layer.update()
    char.dims = {"thigh": thigh, "shin": (ankle - knee).length, "drop": drop, "seat_h": seat_h, "hip_half": half}
    poles = char.rig["poles"]
    leg_pole = leg_pole or poles["leg"]
    arm_pole = arm_pole or poles["arm"]
    for side, s in (("L", 1), ("R", -1)):
        y = s * half
        char.ik("leg", side, (thigh * 0.95, y * 1.1, drop + 0.07), (thigh + 0.6, y * 1.3, drop + seat_h + 0.3),
                pole_angle=leg_pole[side])
        char.ik("arm", side, (thigh * 0.55, y * 1.4, drop + seat_h + 0.16), (-0.4, y * 5, drop + seat_h + 0.3),
                pole_angle=arm_pole[side])
        char.hand_aim(side)
        char.touch(side, 1, on=False)     # はじめは両手ともひざの上
    return drop


def lap(char: Character, side: str):
    """座っているときの、手をひざの上に置く行き先（人形の向き基準）。"""
    d = char.dims
    s = 1 if side == "L" else -1
    return (d["thigh"] * 0.55, s * d["hip_half"] * 1.4, d["drop"] + d["seat_h"] + 0.16)


def stand(char: Character, loc, facing: float, leg_pole=None, arm_pole=None):
    """立たせる：足を腰の真下の床に、手を体の横に下げる。歩かせるときは walk。"""
    char.put(loc, facing)
    hip = char.bone_world("upper_leg", "L")
    knee = char.bone_world("lower_leg", "L")
    ankle = char.bone_world("lower_leg", "L", tail=True)
    half = (hip - char.bone_world("upper_leg", "R")).length / 2
    sh = char.to_local(char.bone_world("upper_arm", "L"))
    elbow = char.bone_world("lower_arm", "L")
    wrist = char.bone_world("hand", "L")
    arm_len = (elbow - char.bone_world("upper_arm", "L")).length + (wrist - elbow).length
    char.dims = {"thigh": (knee - hip).length, "hip_half": half, "ankle_z": ankle.z, "knee_z": knee.z,
                 "hip_z": hip.z, "sh_y": abs(sh.y), "sh_z": sh.z, "arm_len": arm_len, "drop": 0.0}
    poles = char.rig["poles"]
    leg_pole = leg_pole or poles["leg"]
    arm_pole = arm_pole or poles["arm"]
    for side, s in (("L", 1), ("R", -1)):
        y = s * half
        char.ik("leg", side, (0.0, y, ankle.z), (0.6, y * 1.3, knee.z), pole_angle=leg_pole[side])
        char.ik("arm", side, hang_local(char, side), (-0.4, s * 5 * half, sh.z - 0.3), pole_angle=arm_pole[side])
        char.hand_aim(side)
        char.hang(side, 1)


def hang_local(char: Character, side: str, fwd=0.0):
    """立っているとき、手を体の横に下げた行き先（向き基準）。ひじを少し曲げる。"""
    d = char.dims
    s = 1 if side == "L" else -1
    return (0.03 + fwd, s * (d["sh_y"] + 0.03), d["sh_z"] - d["arm_len"] * 0.9)


def walk(char: Character, F, t0: float, t1: float, to_xy, stride=0.6, lift=0.07, swing=0.12,
         free_arms=("L", "R"), turn=0.4):
    """t0〜t1 秒に、今の場所から to_xy（世界の x, y）まで歩く。歩幅 stride（m、1歩）。
    体は等速で進み、足は1歩ずつ交互に前へ出す（足の行き先は place の子なので、着いている足は後ろへ流す）。
    free_arms の腕は足と逆に振る（杖や物を持つ手は外す）。歩き終えたら両足をそろえる。"""
    f0, f1 = F(t0), F(t1)
    start = char.place_matrix(f0).translation.copy()
    end = Vector((to_xy[0], to_xy[1], start.z))
    d = end - start
    dist = d.length
    if dist < 1e-4:
        return
    facing = math.atan2(d.y, d.x)
    # 向きを変えてから歩き出す
    char.face(F(t0 - turn), char.place.rotation_euler.z - math.pi / 2)
    char.face(f0, facing)
    char.face(f1, facing)     # 歩いているあいだは進む向きのまま（あとの向きのキーに引っぱられない）
    # 体：等速で進む
    pl = char.place
    pl.location = start
    pl.keyframe_insert("location", frame=f0)
    pl.location = end
    pl.keyframe_insert("location", frame=f1)
    set_interp(pl, [f0], "LINEAR", path="location")
    n = max(1, round(dist / stride))
    step = dist / n
    dt = (t1 - t0) / n
    dims = char.dims
    half, z0 = dims["hip_half"], dims["ankle_z"] - dims["drop"]

    def body(t):
        return dist * min(max((t - t0) / (t1 - t0), 0.0), 1.0)

    def key_foot(side, t, along, up=0.0):
        y = half if side == "L" else -half
        char.move("leg", side, F(t), target_local=(along - body(t), y, z0 + up), kind="LINEAR", hold=False)

    feet = {"L": 0.0, "R": 0.0}
    order = ("L", "R")
    for side in order:
        key_foot(side, t0, 0.0)
    for k in range(n):
        side = order[k % 2]
        other = order[(k + 1) % 2]
        ta, tb = t0 + k * dt, t0 + (k + 1) * dt
        land = min(dist, (k + 1) * step + step / 2)
        key_foot(side, ta, feet[side])
        key_foot(side, (ta + tb) / 2, (feet[side] + land) / 2, lift)
        key_foot(side, tb, land)
        key_foot(other, ta, feet[other])      # 着いている足（体が進むぶん後ろへ流れる）
        key_foot(other, tb, feet[other])
        feet[side] = land
        for arm in free_arms:   # 出した足と同じ側の腕は後ろ、逆側は前
            back = -swing if arm == side else swing
            char.reach(arm, F(tb), local=hang_local(char, arm, back), fingers=(0.15, 0, -1), thumb=(1, 0, 0))
    # 後ろの足をそろえる
    last = order[(n - 1) % 2]
    trail = order[n % 2]
    te = t1 + dt * 0.7
    key_foot(trail, t1, feet[trail])
    key_foot(trail, (t1 + te) / 2, (feet[trail] + dist) / 2, lift)
    key_foot(trail, te, dist)
    key_foot(last, te, dist)
    for arm in free_arms:
        char.reach(arm, F(te), local=hang_local(char, arm), fingers=(0.15, 0, -1), thumb=(1, 0, 0))


def text(name, body, size, loc, mat, rot=(0, 0, 0), extrude=0.001, font="KleeOne-SemiBold.ttf", parent=None):
    """文字（日本語可）。assets/fonts のフォントで、中央寄せ。立てるなら rot=(π/2, 0, 向き)。
    Noto Serif JP（OTF）は Blender では本来の4割ほどの大きさになるので、TTF の Klee One を使う。"""
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.font = bpy.data.fonts.load(str(REPO / "assets" / "fonts" / font), check_existing=True)
    cu.size = size
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.extrude = extrude
    o = bpy.data.objects.new(name, cu)
    col().objects.link(o)
    o.data.materials.append(mat)
    o.parent = parent
    o.location = loc
    o.rotation_euler = rot
    return o


def show(obj, frame: int, on: bool) -> None:
    """そのフレームから、obj（と子）を見せる（on）／隠す。"""
    for o in [obj, *obj.children_recursive]:
        o.hide_render = not on
        o.hide_viewport = not on
        o.keyframe_insert("hide_render", frame=frame)
        o.keyframe_insert("hide_viewport", frame=frame)


# ---- 書き出し ----------------------------------------------------------------

def render(args, scene, F):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.stills == "none":
        return
    if args.stills:
        scene.render.image_settings.file_format = "PNG"
        for s in args.stills.split(","):
            t = float(s)
            scene.frame_set(F(t))
            scene.render.filepath = str(out / f"still_{t:05.1f}.png")
            bpy.ops.render.render(write_still=True)
            print(f"[3d] still {t:.1f}s → {scene.render.filepath}")
        return
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 92
    frames = out / "frames"
    frames.mkdir(exist_ok=True)
    scene.render.filepath = str(frames / "####")
    bpy.ops.render.render(animation=True)
    print(f"[3d] frames {scene.frame_start}..{scene.frame_end} → {frames}")
