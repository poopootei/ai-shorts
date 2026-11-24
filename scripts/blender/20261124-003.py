"""「予約席」（20261124-003）の 3D の舞台。Blender の中で動かす（scripts/render_3d.py から）。

断面の公園（芝生の台）に、ベンチ・木・街灯・植え込みを置く。ベンチには「予約席」のふだ。
人形：私（casual_man）、おばあさん（casual_woman、白髪・杖）、おじいさん（casual_man、白髪・杖）。
1日目の朝（S2〜S6）と、次の日の昼（S7〜）で光を変える。
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
import kit  # noqa: E402
from kit import ball, box, empty, interp, light, material, rod, text, wood  # noqa: E402

args = kit.parse_args()
tl = kit.Timeline(args.timing, args.fps)
S, F, DURATION = tl.S, tl.F, tl.duration
scene = kit.setup_scene(args, DURATION, world_color=(0.45, 0.6, 0.85))

# ---- 材質 --------------------------------------------------------------------

M = {
    "grass": material("grass", (0.20, 0.42, 0.14), rough=1.0),
    "soil": material("soil", (0.30, 0.20, 0.12), rough=1.0),
    "path": material("path", (0.62, 0.55, 0.45), rough=1.0),
    "bench": wood("bench", (0.30, 0.16, 0.07), (0.55, 0.33, 0.16), stretch=(16.0, 1.0, 1.0)),
    "iron": material("iron", (0.05, 0.06, 0.06), rough=0.4),
    "bark": material("bark", (0.22, 0.14, 0.08), rough=0.9),
    "leaf": material("leaf", (0.13, 0.36, 0.10), rough=0.8),
    "leaf2": material("leaf2", (0.18, 0.45, 0.13), rough=0.8),
    "bush": material("bush", (0.10, 0.30, 0.10), rough=0.9),
    "card": material("card", (0.95, 0.93, 0.86), rough=0.7),
    "ink": material("ink", (0.05, 0.04, 0.04), rough=0.6),
    "lamp": material("lamp", (0.95, 0.92, 0.80), rough=0.3, emission=(1.0, 0.85, 0.6), strength=0.0),
    "cane": material("cane", (0.25, 0.13, 0.06), rough=0.5),
}

# ---- 公園 --------------------------------------------------------------------

box("ground", (5.2, 4.2, 0.3), (0, 0.6, -0.15), M["grass"], bevel=0.0)
box("ground_cut", (5.22, 4.22, 0.25), (0, 0.6, -0.42), M["soil"], bevel=0.0)
box("path", (5.2, 1.3, 0.01), (0, -0.35, 0.005), M["path"], bevel=0.0)

BENCH = (0.0, 0.62)
SEAT_Z = 0.45
bench = empty("bench", (*BENCH, 0))
for i in range(4):   # 座面の板
    box(f"seat{i}", (1.5, 0.09, 0.03), (0, -0.16 + i * 0.105, SEAT_Z), M["bench"], parent=bench, bevel=0.005)
for i in range(3):   # 背の板
    box(f"back{i}", (1.5, 0.03, 0.09), (0, 0.24, 0.6 + i * 0.12), M["bench"], parent=bench, bevel=0.005)
for sx in (-0.68, 0.68):
    box(f"leg_f{sx}", (0.05, 0.05, SEAT_Z), (sx, -0.16, SEAT_Z / 2), M["iron"], parent=bench, bevel=0.005)
    box(f"leg_b{sx}", (0.05, 0.05, 0.9), (sx, 0.24, 0.45), M["iron"], parent=bench, bevel=0.005)
    box(f"arm{sx}", (0.05, 0.45, 0.04), (sx, 0.04, SEAT_Z + 0.2), M["iron"], parent=bench, bevel=0.005)
    box(f"arm_post{sx}", (0.04, 0.04, 0.2), (sx, -0.16, SEAT_Z + 0.1), M["iron"], parent=bench, bevel=0.005)


def card(name, parent=None):
    """「予約席」のふだ（立てた札）。原点は札の下の辺の中央。"""
    root = empty(name, parent=parent)
    box(f"{name}_board", (0.2, 0.008, 0.12), (0, 0, 0.06), M["card"], parent=root, bevel=0.002)
    text(f"{name}_text", "予約席", 0.05, (0, -0.0045, 0.06), M["ink"], rot=(math.pi / 2, 0, 0), parent=root)
    return root


CARD_AT = (BENCH[0] - 0.05, BENCH[1] - 0.05, SEAT_Z + 0.015)
bench_card = card("bench_card")
bench_card.location = CARD_AT
bench_card.rotation_euler = (-0.15, 0, 0)    # 少し後ろへ傾けて置く

# 木（私が隠れる）
TREE = (-1.75, 0.75)
rod("trunk", 0.13, 2.0, (*TREE, 1.0), M["bark"])
for i, (dx, dy, dz, r) in enumerate([(0, 0, 2.3, 0.75), (0.45, 0.1, 2.0, 0.5), (-0.4, 0.15, 2.1, 0.55),
                                     (0.1, -0.3, 2.55, 0.5), (-0.1, 0.35, 2.7, 0.45)]):
    ball(f"leaf{i}", r, (TREE[0] + dx, TREE[1] + dy, dz), M["leaf" if i % 2 else "leaf2"])
# 街灯・植え込み・奥の木
rod("lamp_post", 0.04, 2.6, (1.55, 1.25, 1.3), M["iron"])
ball("lamp_globe", 0.14, (1.55, 1.25, 2.68), M["lamp"])
for i, (x, y, r) in enumerate([(-0.9, 1.45, 0.35), (-0.4, 1.55, 0.3), (0.6, 1.5, 0.38), (1.1, 1.6, 0.3),
                               (2.2, 0.9, 0.4), (-2.3, -0.9, 0.3)]):
    ball(f"bush{i}", r, (x, y, r * 0.6), M["bush"], scale=(1, 1, 0.8))
rod("trunk2", 0.1, 2.2, (2.1, 2.2, 1.1), M["bark"])
ball("leaf_b", 0.7, (2.1, 2.2, 2.5), M["leaf"])

# ---- 人形 --------------------------------------------------------------------

me = kit.Character("me", "casual_man.glb", "quaternius", 1.70)
grandma = kit.Character("grandma", "casual_woman.glb", "mixamo", 1.50)
grandpa = kit.Character("grandpa", "casual_man.glb", "quaternius", 1.62)
grandma.tint_texture(0.09, 0.2, 0.35, (0.62, 0.62, 0.6))      # 金髪 → 白髪
grandpa.recolor("Hair", (0.6, 0.6, 0.58))
grandpa.recolor("LightBrown", (0.42, 0.36, 0.28))

OFF = (6.0, -6.0)    # 出番の外（画面の外）
kit.stand(me, (*OFF, 0), 0.0)
kit.stand(grandma, (2.9, -0.3, 0), math.pi)
kit.stand(grandpa, (2.9, -0.45, 0), math.pi)
for c in (me, grandma, grandpa):
    c.turn("spine", 1)
    c.turn("neck", 1)


def give_cane(c, name):
    """杖を右手に持たせる（握りから下へ、床まで）。"""
    hz = 0.78 * c.dims["sh_z"] / 1.3
    c.reach("R", 1, local=(0.2, -c.dims["sh_y"] - 0.05, hz), fingers=(1, 0, -0.15), thumb=(0, 0, 1))
    stick = rod(name, 0.012, hz, (0, 0, -hz / 2), M["cane"])
    bpy.ops.object.select_all(action="DESELECT")
    stick.select_set(True)
    bpy.context.view_layer.objects.active = stick
    bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)
    c.hold(stick, "R")
    return stick


cane1 = give_cane(grandma, "cane_grandma")
cane2 = give_cane(grandpa, "cane_grandpa")
for c in (grandma, grandpa):
    c.turn("spine", 1, pitch=0.22)       # 少し腰が曲がっている


def appear(c, t_on, t_off, props=()):
    c.show(1, False)
    c.show(F(t_on), True)
    if t_off:
        c.show(F(t_off), False)
    for p in props:
        kit.show(p, 1, False)
        kit.show(p, F(t_on), True)
        if t_off:
            kit.show(p, F(t_off), False)


# ---- 段取り ------------------------------------------------------------------

DAY1 = S[2]["start"] - 0.3        # ある朝早く
DAY2 = S[7]["start"] - 0.3        # 次の日、昼過ぎ

# ふだ：最初の場面（毎朝）にはある。ある朝は、おばあさんが置くまでない
hand_card = card("hand_card")
kit.show(bench_card, 1, True)
kit.show(bench_card, F(DAY1), False)
PUT = S[4]["start"] + 1.3
kit.show(bench_card, F(PUT), True)

# 私：木のかげから見張る
appear(me, DAY1, None)
me.jump(F(DAY1), (TREE[0] - 0.1, TREE[1] + 0.38), -math.pi / 2 + 0.35)
me.turn("spine", F(DAY1), roll=-0.12)
me.turn("neck", F(DAY1), yaw=-0.5)

# おばあさん：やって来て、ふだを置き、帰る
appear(grandma, S[3]["start"] - 0.4, DAY2, props=(cane1,))
kit.show(hand_card, 1, False)
kit.show(hand_card, F(S[3]["start"] - 0.4), True)
kit.show(hand_card, F(PUT), False)
grandma.hold(hand_card, "L", offset=(0.0, 0.0, 0.0))
hand_card.scale = hand_card.scale * 0.8
stop1 = (BENCH[0] - 0.05, BENCH[1] - 0.5)
kit.walk(grandma, F, S[3]["start"] - 0.3, S[4]["start"] + 0.2, stop1, stride=0.32, free_arms=())
grandma.face(F(S[4]["start"] + 0.6), math.pi / 2)
grandma.turn("spine", F(S[4]["start"] + 0.4), pitch=0.22)
grandma.turn("spine", F(PUT - 0.3), pitch=0.65)
grandma.reach("L", F(S[4]["start"] + 0.4), local=(0.25, 0.18, 0.85), fingers=(1, 0, 0), thumb=(0, 0, 1))
grandma.reach("L", F(PUT), world=(CARD_AT[0], CARD_AT[1] - 0.03, CARD_AT[2] + 0.1), fingers=(1, 0, -0.5),
              thumb=(0, 0, 1))
grandma.turn("spine", F(PUT + 0.5), pitch=0.22)
grandma.hang("L", F(PUT + 0.6))
# 帰りかけたところを呼び止められる
WAIT = (1.45, -0.25)
kit.walk(grandma, F, PUT + 0.9, S[5]["start"] + 1.6, WAIT, stride=0.32, free_arms=("L",))
grandma.face(F(S[5]["start"] + 2.1), math.pi)
# 私が追いかける
kit.walk(me, F, S[5]["start"] + 0.1, S[5]["start"] + 1.8, (WAIT[0] - 0.75, WAIT[1] - 0.05), stride=0.55)
me.turn("spine", F(S[5]["start"] + 0.1))
me.turn("neck", F(S[5]["start"] + 0.1))
me.face(F(S[5]["start"] + 2.1), 0.0)
# 照れくさそうに笑う
grandma.turn("neck", F(S[5]["start"] + 2.3))
grandma.turn("neck", F(S[5]["start"] + 2.8), roll=-0.25, pitch=0.15)
grandma.turn("neck", F(S[5]["start"] + 3.3), roll=-0.2, pitch=0.05)
grandma.turn("neck", F(S[6]["start"] + 1.5), roll=-0.15)
grandma.turn("neck", F(S[6]["start"] + 2.2), yaw=-0.7, roll=-0.1)    # ベンチのほうを見る
grandma.turn("neck", F(S[6]["start"] + 3.8), yaw=-0.7, roll=-0.1)
grandma.turn("neck", F(S[6]["start"] + 4.4), roll=-0.2, pitch=0.1)

# 次の日：私は木のそばで見ている。ふだはベンチにある
me.jump(F(DAY2), (TREE[0] + 0.35, TREE[1] - 0.65), -0.2)
me.turn("neck", F(DAY2), yaw=0.15)
# おじいさん：やって来て、ふだを見て、首をふる
appear(grandpa, S[8]["start"] - 0.3, None, props=(cane2,))
stop2 = (BENCH[0] + 0.1, BENCH[1] - 0.55)
kit.walk(grandpa, F, S[8]["start"] - 0.2, S[9]["start"] + 0.2, stop2, stride=0.32, free_arms=("L",))
grandpa.face(F(S[9]["start"] + 0.7), math.pi / 2)
grandpa.turn("neck", F(S[9]["start"] + 0.6))
grandpa.turn("neck", F(S[9]["start"] + 1.2), pitch=0.35)
t = S[9]["start"] + 1.8
for i in range(4):
    grandpa.turn("neck", F(t), pitch=0.3, yaw=0.28 if i % 2 == 0 else -0.28)
    t += 0.4
grandpa.turn("neck", F(t), pitch=0.3)
grandpa.turn("neck", F(S[10]["start"] + 0.2), pitch=0.05)
grandpa.turn("spine", F(S[10]["start"]), pitch=0.22)
grandpa.turn("spine", F(S[10]["start"] + 0.6), pitch=0.3)

# ---- 光 ----------------------------------------------------------------------

sun = light("sun", "SUN", (0, 0, 5), 3.5, (1.0, 0.92, 0.8), target=(0.4, 0.8, 0))
fill = light("fill", "AREA", (-2.5, -4.0, 3.5), 300, (0.85, 0.9, 1.0), size=4.0, target=(0, 0.3, 0.8))
world_bg = scene.world.node_tree.nodes.get("Background").inputs["Color"]


def light_set(frame, sun_rot, sun_energy, sun_color, sky, fill_energy):
    sun.rotation_euler = sun_rot
    sun.data.energy = sun_energy
    sun.data.color = sun_color
    fill.data.energy = fill_energy
    world_bg.default_value = (*sky, 1)
    sun.keyframe_insert("rotation_euler", frame=frame)
    sun.data.keyframe_insert("energy", frame=frame)
    sun.data.keyframe_insert("color", frame=frame)
    fill.data.keyframe_insert("energy", frame=frame)
    world_bg.keyframe_insert("default_value", frame=frame)


MORNING = ((math.radians(65), 0, math.radians(-50)), 3.0, (1.0, 0.9, 0.75), (0.55, 0.68, 0.85), 260)
DAWN = ((math.radians(78), 0, math.radians(-65)), 2.2, (1.0, 0.72, 0.5), (0.62, 0.55, 0.6), 200)
NOON = ((math.radians(30), 0, math.radians(-20)), 4.5, (1.0, 0.97, 0.92), (0.42, 0.62, 0.92), 300)
light_set(1, *MORNING)
light_set(F(DAY1), *DAWN)
light_set(F(DAY2), *NOON)
for id_ in (sun, sun.data, fill.data, scene.world.node_tree):
    kit.make_constant(id_)

# ---- カメラ ------------------------------------------------------------------

target = empty("cam_target", (0, 0.4, 0.7))
cam_data = bpy.data.cameras.new("cam")
cam_data.lens = 32
cam_data.dof.use_dof = True
cam_data.dof.focus_object = target
cam_data.dof.aperture_fstop = 5.6
cam = bpy.data.objects.new("cam", cam_data)
kit.col().objects.link(cam)
scene.camera = cam
c = cam.constraints.new("TRACK_TO")
c.target = target
c.track_axis = "TRACK_NEGATIVE_Z"
c.up_axis = "UP_Y"

SHOTS = {
    "wide":     ((3.6, -6.4, 3.6), (-0.1, 0.5, 0.8)),
    "wide_in":  ((2.6, -4.8, 2.6), (0.0, 0.5, 0.7)),
    "card":     ((0.12, -0.42, 0.72), (CARD_AT[0], CARD_AT[1], CARD_AT[2] + 0.06)),
    "card_out": ((0.9, -2.2, 1.3), (0.0, 0.6, 0.6)),
    "tree":     ((-0.4, -2.6, 1.5), (-1.6, 0.9, 1.25)),
    "walk":     ((-0.9, -3.2, 1.5), (1.3, -0.1, 0.9)),
    "put":      ((0.75, 1.75, 1.35), (0.0, 0.25, 0.7)),     # ベンチの後ろから、おばあさんの顔を見る
    "chase":    ((0.2, -3.4, 1.7), (0.4, 0.0, 0.95)),
    "talk":     ((0.6, -2.6, 1.45), (1.1, -0.2, 1.1)),
    "grandma":  ((0.55, -1.45, 1.35), (WAIT[0], WAIT[1], 1.2)),
    "noon":     ((2.4, -4.6, 2.4), (0.2, 0.4, 0.8)),
    "grandpa_in": ((-0.8, -3.2, 1.5), (1.2, -0.2, 0.95)),
    "grandpa":  ((0.75, 1.7, 1.4), (0.1, 0.15, 0.95)),     # ベンチの後ろから、おじいさんの顔を見る
    "card_end": ((-0.3, -1.6, 1.25), (0.0, 0.35, 0.8)),
    "final":    ((4.2, -7.2, 4.2), (0.0, 0.5, 0.8)),
}
CUTS = [   # (秒, ショット)。間はなめらかに動く
    (0.0, "wide"), (S[0]["start"] + 1.5, "wide_in"), (S[0]["end"] - 0.6, "card"), (S[1]["start"] + 1.6, "card"),
    (S[1]["end"], "card_out"),
    (DAY1, "tree"), (S[2]["end"], "tree"),
    (S[3]["start"], "walk"), (S[4]["start"], "put"), (S[4]["end"], "put"),
    (S[5]["start"] + 0.2, "chase"), (S[5]["end"], "talk"), (S[6]["start"] + 1.0, "grandma"),
    (S[6]["end"] - 0.2, "grandma"),
    (DAY2, "noon"), (S[7]["end"], "noon"),
    (S[8]["start"], "grandpa_in"), (S[9]["start"], "grandpa"), (S[10]["start"], "card_end"),
    (DURATION, "final"),
]
CUT_HARD = {DAY1, DAY2}    # 場面が変わるところは、パッと切り替える
interp("BEZIER")
for t, name in CUTS:
    loc, tgt = SHOTS[name]
    if t in CUT_HARD:
        f = F(t) - 1
        cam.keyframe_insert("location", frame=f)
        target.keyframe_insert("location", frame=f)
        kit.set_interp(cam, [f], "CONSTANT")
        kit.set_interp(target, [f], "CONSTANT")
    cam.location = loc
    cam.keyframe_insert("location", frame=F(t))
    target.location = tgt
    target.keyframe_insert("location", frame=F(t))

kit.render(args, scene, F)
