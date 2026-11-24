"""「思い出の質屋」（20261123-007）の 3D の舞台。Blender の中で動かす（scripts/render_3d.py から）。

断面の店（床と壁2枚）。左の壁に木の扉と小さな看板（外から見る）。中に帳場（カウンター）と、
奥の壁に思い出の小瓶をならべた棚。思い出は瓶の中の光る玉で表す。
人形：私（casual_woman、こげ茶の髪）、店主（casual_man、白髪）。
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
import kit  # noqa: E402
from kit import ball, box, empty, interp, light, material, rod, text, wood  # noqa: E402

args = kit.parse_args()
tl = kit.Timeline(args.timing, args.fps)
S, F, DURATION = tl.S, tl.F, tl.duration
scene = kit.setup_scene(args, DURATION, world_color=(0.10, 0.09, 0.16))

# ---- 材質 --------------------------------------------------------------------

M = {
    "floor": wood("floor", (0.16, 0.08, 0.03), (0.34, 0.19, 0.08)),
    "wall": material("wall", (0.55, 0.47, 0.36), rough=0.9),
    "wall_out": material("wall_out", (0.42, 0.36, 0.30), rough=0.95),
    "wall_cut": material("wall_cut", (0.22, 0.19, 0.16), rough=0.9),
    "street": material("street", (0.20, 0.20, 0.22), rough=0.95),
    "door": wood("door", (0.18, 0.09, 0.04), (0.36, 0.20, 0.09), stretch=(1.0, 1.0, 12.0)),
    "counter": wood("counter", (0.22, 0.11, 0.05), (0.44, 0.25, 0.11), stretch=(1.0, 12.0, 1.0)),
    "shelf": wood("shelf", (0.25, 0.13, 0.06), (0.46, 0.27, 0.12), stretch=(12.0, 1.0, 1.0)),
    "sign": wood("sign", (0.30, 0.18, 0.08), (0.50, 0.32, 0.15), stretch=(8.0, 1.0, 1.0)),
    "ink": material("ink", (0.04, 0.03, 0.03), rough=0.6),
    "paper": material("paper", (0.90, 0.86, 0.74), rough=0.8),
    "metal": material("metal", (0.55, 0.45, 0.25), rough=0.3),
    "iron": material("iron", (0.05, 0.05, 0.05), rough=0.4),
    "lid": material("lid", (0.20, 0.14, 0.08), rough=0.5),
    "lens": material("lens", (0.85, 0.92, 1.0), rough=0.02),
    "shade": material("shade", (0.95, 0.80, 0.55), rough=0.6, emission=(1.0, 0.7, 0.4), strength=3.0),
    "book": material("book", (0.25, 0.08, 0.06), rough=0.6),
    "street_lamp": material("street_lamp", (1, 0.9, 0.7), emission=(1.0, 0.8, 0.5), strength=4.0),
}
glass = material("glass", (0.85, 0.92, 0.95), rough=0.05)
glass.node_tree.nodes.get("Principled BSDF").inputs["Alpha"].default_value = 0.22
M["glass"] = glass
lens_bsdf = M["lens"].node_tree.nodes.get("Principled BSDF")
lens_bsdf.inputs["Alpha"].default_value = 0.25

# ---- 店 ----------------------------------------------------------------------

WALL_X, BACK_Y, WALL_H = -2.0, 1.6, 2.6
DOOR_Y0, DOOR_Y1, DOOR_H = -0.75, 0.15, 2.05
box("floor", (4.2, 3.6, 0.2), (0.1, -0.1, -0.1), M["floor"], bevel=0.0)
box("floor_cut", (4.22, 3.62, 0.12), (0.1, -0.1, -0.27), M["wall_cut"], bevel=0.0)
box("street", (3.0, 4.6, 0.1), (WALL_X - 1.6, -0.3, -0.06), M["street"], bevel=0.0)
box("wall_back", (4.2, 0.15, WALL_H), (0.1, BACK_Y + 0.075, WALL_H / 2), M["wall"], bevel=0.0)
# 左の壁（扉の穴をあける）。外側の面は少し暗い色の板を重ねる
for name, y0, y1, z0, z1 in (("a", -1.9, DOOR_Y0, 0, WALL_H), ("b", DOOR_Y1, BACK_Y + 0.15, 0, WALL_H),
                             ("c", DOOR_Y0, DOOR_Y1, DOOR_H, WALL_H)):
    box(f"wall_left_{name}", (0.15, y1 - y0, z1 - z0), (WALL_X - 0.075, (y0 + y1) / 2, (z0 + z1) / 2),
        M["wall"], bevel=0.0)
    box(f"wall_out_{name}", (0.02, y1 - y0, z1 - z0), (WALL_X - 0.16, (y0 + y1) / 2, (z0 + z1) / 2),
        M["wall_out"], bevel=0.0)
box("wall_back_top", (4.22, 0.17, 0.03), (0.1, BACK_Y + 0.075, WALL_H + 0.015), M["wall_cut"], bevel=0.0)
box("wall_left_top", (0.19, 3.52, 0.03), (WALL_X - 0.08, -0.12, WALL_H + 0.015), M["wall_cut"], bevel=0.0)
for y in (DOOR_Y0 - 0.04, DOOR_Y1 + 0.04):      # 扉の枠
    box(f"door_post{y}", (0.2, 0.08, DOOR_H), (WALL_X - 0.08, y, DOOR_H / 2), M["door"], bevel=0.005)
box("door_lintel", (0.2, DOOR_Y1 - DOOR_Y0 + 0.16, 0.08), (WALL_X - 0.08, (DOOR_Y0 + DOOR_Y1) / 2, DOOR_H + 0.04),
    M["door"], bevel=0.005)
hinge = empty("door_hinge", (WALL_X - 0.05, DOOR_Y0, 0))
box("door", (0.05, DOOR_Y1 - DOOR_Y0, DOOR_H - 0.02), (0, (DOOR_Y1 - DOOR_Y0) / 2, DOOR_H / 2), M["door"],
    parent=hinge, bevel=0.006)
ball("door_knob", 0.03, (-0.06, DOOR_Y1 - DOOR_Y0 - 0.12, 1.0), M["metal"], parent=hinge)
# 小さな看板（外の壁。左から見て読める向き）
SIGN = (WALL_X - 0.2, DOOR_Y1 + 0.38, 1.75)
rod("sign_bar", 0.012, 0.25, (WALL_X - 0.2, SIGN[1], 2.05), M["iron"], rot=(0, math.pi / 2, 0))
box("sign_board", (0.03, 0.34, 0.3), SIGN, M["sign"], bevel=0.008)
text("sign_text", "質", 0.17, (SIGN[0] - 0.017, SIGN[1], SIGN[2] + 0.02), M["ink"], rot=(math.pi / 2, 0, -math.pi / 2))
text("sign_text2", "おもいで", 0.045, (SIGN[0] - 0.017, SIGN[1], SIGN[2] - 0.1), M["ink"],
     rot=(math.pi / 2, 0, -math.pi / 2))
rod("street_lamp_post", 0.04, 2.8, (WALL_X - 2.2, -1.6, 1.4), M["iron"])
ball("street_lamp_globe", 0.13, (WALL_X - 2.2, -1.6, 2.85), M["street_lamp"])

# 帳場（カウンター）
CX, CY, CW, CL, CH = 0.62, 0.45, 0.5, 1.7, 0.95
box("counter", (CW, CL, CH), (CX, CY, CH / 2), M["counter"], bevel=0.01)
box("counter_top", (CW + 0.08, CL + 0.08, 0.04), (CX, CY, CH + 0.02), M["counter"], bevel=0.008)
TOP = CH + 0.04

# 棚と思い出の瓶
rng = random.Random(3)
COLORS = [(1.0, 0.55, 0.2), (0.4, 0.8, 1.0), (0.6, 1.0, 0.5), (1.0, 0.85, 0.3), (0.85, 0.5, 1.0),
          (1.0, 0.4, 0.35), (0.5, 0.95, 0.9)]


def jar(name, loc, color, strength=1.5, parent=None, scale=1.0):
    """思い出の瓶。原点は瓶の底。中の玉の材質を返す（色あせさせるときに使う）。"""
    root = empty(name, loc, parent=parent)
    root.scale = (scale, scale, scale)
    rod(f"{name}_glass", 0.05, 0.12, (0, 0, 0.06), M["glass"], parent=root)
    rod(f"{name}_lid", 0.053, 0.022, (0, 0, 0.13), M["lid"], parent=root)
    mem = material(f"{name}_mem", tuple(c * 0.6 for c in color), rough=0.4, emission=color, strength=strength)
    ball(f"{name}_mem", 0.034, (0, 0, 0.055), mem, parent=root)
    return root, mem


SHELF_Z = (1.15, 1.55, 1.95)
SHELF_X = (-1.85, 1.35)
for z in SHELF_Z:
    box(f"shelf{z}", (SHELF_X[1] - SHELF_X[0], 0.26, 0.03), ((SHELF_X[0] + SHELF_X[1]) / 2, BACK_Y - 0.13, z),
        M["shelf"], bevel=0.004)
for x in (SHELF_X[0], 0.0 - 0.25, SHELF_X[1]):
    box(f"shelf_side{x}", (0.03, 0.26, 1.0), (x, BACK_Y - 0.13, 1.5), M["shelf"], bevel=0.004)
THE_JAR = (-1.05, BACK_Y - 0.14, SHELF_Z[2] + 0.015)      # あの人の名前の瓶
for zi, z in enumerate(SHELF_Z):
    x = SHELF_X[0] + 0.12
    while x < SHELF_X[1] - 0.1:
        if abs(x - THE_JAR[0]) > 0.1 or zi != 2:
            if rng.random() < 0.8:
                jar(f"jar_{zi}_{x:.2f}", (x, BACK_Y - 0.14 + rng.uniform(-0.03, 0.03), z + 0.015),
                    rng.choice(COLORS), strength=rng.uniform(0.25, 0.7), scale=rng.uniform(0.85, 1.15))
        x += rng.uniform(0.15, 0.22)
the_jar, the_mem = jar("the_jar", THE_JAR, (0.8, 0.55, 0.62), strength=0.25)
box("the_label", (0.07, 0.004, 0.045), (THE_JAR[0], THE_JAR[1] - 0.052, THE_JAR[2] + 0.07), M["paper"], bevel=0.0)
for i in range(3):     # 名前（手書きの線）
    box(f"the_label_ink{i}", (0.012, 0.003, 0.028), (THE_JAR[0] - 0.02 + i * 0.02, THE_JAR[1] - 0.055,
                                                     THE_JAR[2] + 0.07), M["ink"], bevel=0.0)

# 帳面（店主の左手の前）
BOOK = (CX + 0.1, CY + 0.5, TOP)
box("book_cover", (0.26, 0.36, 0.012), (BOOK[0], BOOK[1], TOP + 0.006), M["book"], bevel=0.003)
box("book_pages_l", (0.24, 0.17, 0.018), (BOOK[0], BOOK[1] - 0.088, TOP + 0.02), M["paper"], bevel=0.002)
box("book_pages_r", (0.24, 0.17, 0.018), (BOOK[0], BOOK[1] + 0.088, TOP + 0.02), M["paper"], bevel=0.002)
page_hinge = empty("page_hinge", (BOOK[0], BOOK[1], TOP + 0.03))
box("page", (0.235, 0.165, 0.002), (0, 0.085, 0), M["paper"], parent=page_hinge, bevel=0.0)
for i in range(4):
    box(f"page_ink{i}", (0.15, 0.004, 0.001), (0.0, 0.03 + i * 0.03, 0.0015), M["ink"], parent=page_hinge, bevel=0.0)

# 照明の笠
for x in (-0.9, CX):
    rod(f"cord{x}", 0.006, 0.6, (x, CY, WALL_H - 0.3), M["iron"])
    kit.cone(f"shade{x}", 0.16, 0.04, 0.14, (x, CY, WALL_H - 0.66), M["shade"])

# ---- 人形 --------------------------------------------------------------------

me = kit.Character("me", "casual_woman.glb", "mixamo", 1.58)
keeper = kit.Character("keeper", "casual_man.glb", "quaternius", 1.66)
me.tint_texture(0.09, 0.2, 0.35, (0.05, 0.025, 0.015))     # 金髪 → こげ茶の髪
keeper.recolor("Hair", (0.68, 0.68, 0.66))
keeper.recolor("LightBrown", (0.22, 0.17, 0.13))

HERE = (CX - CW / 2 - 0.32, CY)           # 私が立つ所（帳場の前）
KEEP = (CX + CW / 2 + 0.3, CY - 0.05)     # 店主
kit.stand(me, (WALL_X - 0.9, -0.3, 0), 0.0)
kit.stand(keeper, (*KEEP, 0), math.pi)
for c in (me, keeper):
    c.turn("spine", 1)
    c.turn("neck", 1)

# 私の思い出（手に持つ瓶と、帳場に置いた瓶）
# 明るすぎると色調補正（AgX）で白っぽくなるので、発光は弱め
my_jar_hand, my_mem_hand = jar("my_jar_hand", (0, 0, 0), (1.0, 0.12, 0.35), strength=1.0)
my_jar_top, my_mem_top = jar("my_jar_top", (CX - 0.1, CY, TOP), (1.0, 0.12, 0.35), strength=1.0)
for ob in my_jar_hand.children:     # 手の中で、瓶の底が握る所の少し下に来るように
    ob.location.z -= 0.06
me.reach("R", 1, local=(0.25, -0.12, 1.0), fingers=(1, 0.3, 0), thumb=(0, 0, 1))
me.hold(my_jar_hand, "R", offset=(0.0, 0.0, 0.0))

# 虫めがね（店主の右手）
glass_root = empty("magnifier")
rod("mag_handle", 0.012, 0.12, (0, 0, -0.02), M["lid"], parent=glass_root)
bpy.ops.mesh.primitive_torus_add(major_radius=0.05, minor_radius=0.006, location=(0, 0, 0.09))
ring = bpy.context.active_object
ring.name = "mag_ring"
ring.rotation_euler = (math.pi / 2, 0, 0)
ring.data.materials.append(M["metal"])
ring.parent = glass_root
rod("mag_lens", 0.048, 0.004, (0, 0, 0.09), M["lens"], parent=glass_root, rot=(math.pi / 2, 0, 0))
keeper.reach("R", 1, local=(0.18, -0.2, 0.95), fingers=(1, 0, -0.3), thumb=(0, 0, 1))
keeper.hold(glass_root, "R")


def talk(c, t0, t1, amount=0.08):
    """話している：首を小さくうなずかせる。"""
    t = t0
    while t < t1 - 0.3:
        c.turn("neck", F(t), pitch=amount)
        c.turn("neck", F(t + 0.25), pitch=0.0)
        t += 0.55


def swap(a, b, t):
    """t 秒で a を隠して b を見せる（手に持った物を置く・取るとき）。"""
    kit.show(a, F(t), False)
    kit.show(b, F(t), True)


# ---- 段取り ------------------------------------------------------------------

# 扉が開いて、私が入ってくる（それまでは外にもいない）
me.show(1, False)
me.show(F(S[2]["start"] - 0.2), True)
kit.show(my_jar_top, 1, False)
kit.show(my_jar_hand, 1, False)
kit.show(my_jar_hand, F(S[2]["start"] - 0.2), True)
interp("BEZIER")
hinge.rotation_euler = (0, 0, 0)
hinge.keyframe_insert("rotation_euler", frame=F(S[2]["start"] - 0.2))
hinge.rotation_euler = (0, 0, -1.4)
hinge.keyframe_insert("rotation_euler", frame=F(S[2]["start"] + 0.8))
hinge.keyframe_insert("rotation_euler", frame=F(S[3]["start"]))
hinge.rotation_euler = (0, 0, 0)
hinge.keyframe_insert("rotation_euler", frame=F(S[3]["start"] + 1.2))
kit.walk(me, F, S[2]["start"] + 0.5, S[2]["end"] + 0.2, HERE, stride=0.55, free_arms=("L",))
# 帳場に瓶を置く
PUT = S[3]["start"] - 0.1
me.reach("R", F(PUT - 0.5), local=(0.25, -0.12, 1.0), fingers=(1, 0.3, 0), thumb=(0, 0, 1))
me.reach("R", F(PUT), world=(CX - 0.1, CY - 0.04, TOP + 0.08), fingers=(1, 0, 0), thumb=(0, 0, 1))
swap(my_jar_hand, my_jar_top, PUT)
me.hang("R", F(PUT + 0.6))
# 店主が虫めがねで見る
LOOK0, LOOK1 = S[3]["start"] + 0.3, S[3]["end"] + 0.1
keeper.turn("spine", F(LOOK0 - 0.4))
keeper.turn("spine", F(LOOK0 + 0.4), pitch=0.4)
keeper.turn("neck", F(LOOK0 + 0.4), pitch=0.25)
keeper.reach("R", F(LOOK0 - 0.3), local=(0.18, -0.2, 0.95), fingers=(1, 0, -0.3), thumb=(0, 0, 1))
keeper.reach("R", F(LOOK0 + 0.5), world=(CX - 0.06, CY - 0.06, TOP + 0.1), fingers=(1, 0, 0), thumb=(0, 0, 1))
keeper.reach("R", F(LOOK1), world=(CX - 0.04, CY - 0.03, TOP + 0.12), fingers=(1, 0, 0), thumb=(0, 0, 1))
keeper.reach("R", F(LOOK1 + 0.5), local=(0.18, -0.2, 0.95), fingers=(1, 0, -0.3), thumb=(0, 0, 1))
keeper.turn("spine", F(LOOK1 + 0.5))
keeper.turn("neck", F(LOOK1 + 0.3), pitch=0.2)
# 首を横にふる
t = S[4]["start"] + 0.3
keeper.turn("neck", F(t - 0.2))
for i in range(4):
    keeper.turn("neck", F(t), yaw=0.3 if i % 2 == 0 else -0.3)
    t += 0.35
keeper.turn("neck", F(t))
talk(keeper, S[5]["start"], S[5]["end"])
# 私が聞く（身を乗り出す）
me.turn("spine", F(S[6]["start"]))
me.turn("spine", F(S[6]["start"] + 0.4), pitch=0.2)
me.turn("neck", F(S[6]["start"] + 0.4), roll=0.15)
me.turn("spine", F(S[6]["end"] + 0.2))
me.turn("neck", F(S[6]["end"] + 0.2))
talk(keeper, S[7]["start"], S[7]["end"])
# 帳面をめくる
keeper.reach("L", F(S[8]["start"] - 0.2), local=kit.hang_local(keeper, "L"), fingers=(0.15, 0, -1),
             thumb=(1, 0, 0))
keeper.reach("L", F(S[8]["start"] + 0.3), world=(BOOK[0] - 0.05, BOOK[1] + 0.1, TOP + 0.06),
             fingers=(1, 0.2, -0.3), thumb=(0, -1, 0))
keeper.turn("neck", F(S[8]["start"]))
keeper.turn("neck", F(S[8]["start"] + 0.4), pitch=0.35, yaw=-0.3)
for i, t in enumerate((S[8]["start"] + 0.5, S[8]["start"] + 1.4)):
    page_hinge.rotation_euler = (0, 0, 0)
    page_hinge.keyframe_insert("rotation_euler", frame=F(t))
    page_hinge.rotation_euler = (-math.pi, 0, 0)
    page_hinge.keyframe_insert("rotation_euler", frame=F(t + 0.6))
    kit.set_interp(page_hinge, [F(t + 0.6)], "CONSTANT")
keeper.reach("L", F(S[9]["start"]), world=(BOOK[0] - 0.05, BOOK[1] - 0.05, TOP + 0.06),
             fingers=(1, 0.2, -0.3), thumb=(0, -1, 0))
keeper.turn("neck", F(S[9]["start"] + 0.3), pitch=0.1)
talk(keeper, S[9]["start"] + 0.3, S[9]["end"])
keeper.hang("L", F(S[9]["end"] + 0.3))
# 私は瓶を持って帰る。帰りぎわ、棚を見上げる
TAKE = S[9]["end"] + 0.2
me.reach("R", F(TAKE - 0.5), local=kit.hang_local(me, "R"), fingers=(0.15, 0, -1), thumb=(1, 0, 0))
me.reach("R", F(TAKE), world=(CX - 0.1, CY - 0.04, TOP + 0.08), fingers=(1, 0, 0), thumb=(0, 0, 1))
swap(my_jar_top, my_jar_hand, TAKE)
me.reach("R", F(TAKE + 0.5), local=(0.25, -0.12, 1.0), fingers=(1, 0.3, 0), thumb=(0, 0, 1))
STOP = (THE_JAR[0] + 0.05, 0.75)
kit.walk(me, F, S[10]["start"], S[10]["start"] + 1.6, STOP, stride=0.5, free_arms=("L",))
me.face(F(S[10]["start"] + 2.0), math.pi / 2)
me.turn("neck", F(S[10]["start"] + 1.8))
me.turn("neck", F(S[10]["start"] + 2.4), pitch=-0.45)
me.turn("neck", F(DURATION), pitch=-0.4)
# 瓶を胸の前に上げて見くらべる
me.reach("R", F(S[12]["start"]), local=(0.25, -0.12, 1.0), fingers=(1, 0.3, 0), thumb=(0, 0, 1))
me.reach("R", F(S[12]["start"] + 0.8), local=(0.3, -0.05, 1.18), fingers=(1, 0.3, 0), thumb=(0, 0, 1))
# あの人の瓶は、いっそう色あせる
sock = kit.emission_socket(the_mem)
col_sock = the_mem.node_tree.nodes.get("Principled BSDF").inputs["Emission Color"]
sock.keyframe_insert("default_value", frame=F(S[12]["start"]))
col_sock.keyframe_insert("default_value", frame=F(S[12]["start"]))
sock.default_value = 0.04
col_sock.default_value = (0.6, 0.58, 0.58, 1)
sock.keyframe_insert("default_value", frame=F(S[12]["end"]))
col_sock.keyframe_insert("default_value", frame=F(S[12]["end"]))

# ---- 光 ----------------------------------------------------------------------

for x in (-0.9, CX):
    light(f"bulb{x}", "POINT", (x, CY, WALL_H - 0.72), 70, (1.0, 0.72, 0.45), size=0.1)
light("fill", "AREA", (1.5, -3.5, 3.5), 140, (1.0, 0.85, 0.7), size=3.0, target=(0, 0.4, 1.0))
light("fill_front", "AREA", (-1.5, -2.8, 2.4), 70, (1.0, 0.88, 0.75), size=2.0, target=(CX + 0.6, CY, 1.2))
light("street_light", "POINT", (WALL_X - 2.2, -1.6, 2.7), 90, (1.0, 0.75, 0.45), size=0.2)
light("outside", "AREA", (WALL_X - 3.5, -2.0, 3.0), 120, (0.55, 0.6, 0.95), size=3.0, target=(WALL_X, -0.2, 1.2))
light("shelf_glow", "AREA", (-0.2, BACK_Y - 0.9, 2.4), 40, (1.0, 0.8, 0.6), size=2.0, target=(-0.2, BACK_Y, 1.5))

# ---- カメラ ------------------------------------------------------------------

target = empty("cam_target", (0, 0, 1))
cam_data = bpy.data.cameras.new("cam")
cam_data.lens = 32
cam_data.dof.use_dof = True
cam_data.dof.focus_object = target
cam_data.dof.aperture_fstop = 4.0
cam = bpy.data.objects.new("cam", cam_data)
kit.col().objects.link(cam)
scene.camera = cam
c = cam.constraints.new("TRACK_TO")
c.target = target
c.track_axis = "TRACK_NEGATIVE_Z"
c.up_axis = "UP_Y"

SHOTS = {
    "street":    ((WALL_X - 5.0, -4.2, 2.6), (WALL_X, -0.2, 1.3)),
    "door":      ((WALL_X - 2.6, -1.3, 1.55), (WALL_X - 0.1, -0.05, 1.45)),
    "sign":      ((WALL_X - 1.4, -0.2, 1.75), (SIGN[0], SIGN[1] - 0.15, 1.65)),
    "enter":     ((1.8, -3.9, 2.9), (-0.7, 0.2, 0.9)),
    "counter":   ((0.55, -2.4, 1.65), (CX, CY, 1.1)),
    "magnify":   ((0.25, -0.7, 1.3), (CX - 0.05, CY, 1.05)),
    "keeper":    ((-0.3, -1.1, 1.5), (KEEP[0], KEEP[1], 1.35)),
    "me":        ((1.5, -1.0, 1.45), (HERE[0], HERE[1], 1.3)),
    "book":      ((0.2, 0.05, 1.65), (BOOK[0] + 0.1, BOOK[1], TOP + 0.15)),
    "leave":     ((1.0, -3.0, 1.9), (-0.8, 0.6, 1.4)),
    "the_jar":   ((THE_JAR[0] + 0.2, THE_JAR[1] - 0.7, THE_JAR[2] + 0.05), (THE_JAR[0], THE_JAR[1], THE_JAR[2] + 0.06)),
    "both":      ((0.75, 0.75, 1.55), (THE_JAR[0] + 0.1, 1.1, 1.6)),     # 棚の横から、私の顔と瓶
    "final":     ((1.6, -3.4, 2.4), (-0.6, 0.8, 1.4)),
}
CUTS = [
    (0.0, "street"), (S[0]["end"], "door"), (S[1]["start"] + 1.2, "sign"), (S[1]["end"], "sign"),
    (S[2]["start"], "enter"), (S[2]["end"], "counter"),
    (S[3]["start"] + 0.3, "magnify"), (S[3]["end"], "magnify"),
    (S[4]["start"], "keeper"), (S[5]["end"], "keeper"),
    (S[6]["start"], "me"), (S[6]["end"], "me"),
    (S[7]["start"], "keeper"), (S[7]["end"], "counter"),
    (S[8]["start"], "book"), (S[8]["end"], "book"),
    (S[9]["start"] + 0.2, "keeper"), (S[9]["end"], "counter"),
    (S[10]["start"] + 0.3, "leave"), (S[10]["end"] + 0.2, "the_jar"), (S[11]["end"], "the_jar"),
    (S[12]["start"] + 0.6, "both"), (S[12]["end"], "both"), (DURATION, "final"),
]
CUT_HARD = {S[2]["start"]}      # 外 → 中は、パッと切り替える
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
