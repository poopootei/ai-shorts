"""「二人目の僕」（20261123-008）の 3D の舞台。Blender の中で動かす（scripts/render_3d.py から）。

断面の2部屋を横にならべる：左が僕の家（ソファ・テーブル）、右が会社（机・パソコン）。間の壁に戸口。
人形：僕（casual_man、ソファに座ったまま）、クローン（casual_man。届いて歩く版と、会社で座る版の2体）、
妻（casual_woman、こげ茶の髪。最後に出る）。
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
scene = kit.setup_scene(args, DURATION, world_color=(0.04, 0.05, 0.09))

# ---- 材質 --------------------------------------------------------------------

M = {
    "floor_home": wood("floor_home", (0.24, 0.13, 0.06), (0.45, 0.27, 0.13)),
    "floor_office": material("floor_office", (0.32, 0.34, 0.36), rough=0.9),
    "wall_home": material("wall_home", (0.80, 0.74, 0.62), rough=0.9),
    "wall_office": material("wall_office", (0.78, 0.80, 0.82), rough=0.9),
    "wall_cut": material("wall_cut", (0.28, 0.26, 0.24), rough=0.9),
    "sofa": material("sofa", (0.20, 0.32, 0.45), rough=0.9),
    "table": wood("table", (0.30, 0.17, 0.08), (0.52, 0.32, 0.16), stretch=(10.0, 1.0, 1.0)),
    "desk": material("desk", (0.85, 0.84, 0.80), rough=0.5),
    "metal": material("metal", (0.15, 0.15, 0.16), rough=0.35),
    "chair": material("chair", (0.12, 0.12, 0.13), rough=0.6),
    "cardboard": material("cardboard", (0.62, 0.45, 0.26), rough=0.9),
    "tape": material("tape", (0.75, 0.62, 0.40), rough=0.5),
    "screen": material("screen", (0.05, 0.08, 0.12), rough=0.2, emission=(0.45, 0.7, 1.0), strength=0.8),
    "phone": material("phone", (0.04, 0.04, 0.05), rough=0.3),
    "phone_screen": material("phone_screen", (0.05, 0.08, 0.1), rough=0.2, emission=(0.5, 0.75, 1.0), strength=0.6),
    "plate": material("plate", (0.15, 0.12, 0.08), rough=0.4),
    "gold": material("gold", (0.9, 0.7, 0.25), rough=0.3, emission=(1.0, 0.75, 0.3), strength=0.2),
    "zzz": material("zzz", (0.95, 0.95, 1.0), rough=0.5, emission=(0.9, 0.9, 1.0), strength=0.4),
    "yen": material("yen", (0.2, 0.8, 0.3), rough=0.5, emission=(0.2, 1.0, 0.35), strength=0.6),
    "window": material("window", (0.3, 0.5, 0.8), rough=0.2, emission=(0.55, 0.75, 1.0), strength=1.2),
    "frame": material("frame", (0.92, 0.90, 0.86), rough=0.5),
    "plant": material("plant", (0.12, 0.35, 0.14), rough=0.8),
    "pot": material("pot", (0.85, 0.85, 0.82), rough=0.6),
}

# ---- 部屋 --------------------------------------------------------------------

X0, X1, BACK_Y, WALL_H = -3.2, 3.2, 1.5, 2.5
DOOR_Y0, DOOR_Y1 = -0.75, 0.35
box("floor_home", (3.2, 3.2, 0.2), (X0 / 2, -0.1, -0.1), M["floor_home"], bevel=0.0)
box("floor_office", (3.2, 3.2, 0.2), (X1 / 2, -0.1, -0.1), M["floor_office"], bevel=0.0)
box("floor_cut", (6.42, 3.22, 0.12), (0, -0.1, -0.27), M["wall_cut"], bevel=0.0)
box("wall_back_home", (3.2, 0.15, WALL_H), (X0 / 2, BACK_Y + 0.075, WALL_H / 2), M["wall_home"], bevel=0.0)
box("wall_back_office", (3.2, 0.15, WALL_H), (X1 / 2, BACK_Y + 0.075, WALL_H / 2), M["wall_office"], bevel=0.0)
box("wall_left", (0.15, 3.35, WALL_H), (X0 - 0.075, -0.03, WALL_H / 2), M["wall_home"], bevel=0.0)
for name, y0, y1, z0, z1 in (("a", -1.7, DOOR_Y0, 0, WALL_H), ("b", DOOR_Y1, BACK_Y, 0, WALL_H),
                             ("c", DOOR_Y0, DOOR_Y1, 2.05, WALL_H)):
    box(f"wall_mid_{name}", (0.15, y1 - y0, z1 - z0), (0, (y0 + y1) / 2, (z0 + z1) / 2), M["wall_cut"], bevel=0.0)
box("wall_top", (6.6, 0.17, 0.03), (0, BACK_Y + 0.075, WALL_H + 0.015), M["wall_cut"], bevel=0.0)
windows = []
for x in (-1.6, 1.6):
    box(f"wframe{x}", (1.1, 0.05, 1.0), (x, BACK_Y - 0.01, 1.5), M["frame"], bevel=0.008)
    windows.append(box(f"window{x}", (0.98, 0.05, 0.88), (x, BACK_Y - 0.03, 1.5), M["window"], bevel=0.0))

# 家：ソファ・テーブル・観葉植物
SOFA = (-1.6, 0.75)
box("sofa_base", (1.7, 0.8, 0.3), (SOFA[0], SOFA[1], 0.15), M["sofa"], bevel=0.04)
box("sofa_seat", (1.5, 0.7, 0.14), (SOFA[0], SOFA[1] - 0.02, 0.37), M["sofa"], bevel=0.05)
box("sofa_back", (1.7, 0.22, 0.5), (SOFA[0], SOFA[1] + 0.33, 0.62), M["sofa"], bevel=0.06)
for sx in (-0.82, 0.82):
    box(f"sofa_arm{sx}", (0.18, 0.8, 0.32), (SOFA[0] + sx, SOFA[1], 0.5), M["sofa"], bevel=0.06)
TABLE = (-1.6, -0.1)
kit.table("low_table", TABLE, (0.9, 0.45), 0.4, M["table"])
rod("pot", 0.13, 0.3, (-2.75, 1.15, 0.15), M["pot"])
ball("plant", 0.3, (-2.75, 1.15, 0.6), M["plant"], scale=(1, 1, 1.4))

# 会社：机・椅子・パソコン・名札
DESK = (1.55, 0.4)
DESK_Z = 0.74
box("desk_top", (1.3, 0.65, 0.04), (DESK[0], DESK[1], DESK_Z - 0.02), M["desk"], bevel=0.005)
for sx in (-0.6, 0.6):
    box(f"desk_leg{sx}", (0.04, 0.6, DESK_Z - 0.04), (DESK[0] + sx, DESK[1], (DESK_Z - 0.04) / 2), M["metal"], bevel=0.0)
box("desk_front", (1.2, 0.02, 0.4), (DESK[0], DESK[1] - 0.3, DESK_Z - 0.25), M["desk"], bevel=0.0)
kit.chair("office_chair", (DESK[0], DESK[1] + 0.62, 0), -math.pi / 2, M["chair"])
monitor = empty("monitor", (DESK[0] - 0.38, DESK[1] + 0.05, DESK_Z), rot=(0, 0, -0.5))
box("mon_stand", (0.05, 0.05, 0.25), (0, 0, 0.125), M["metal"], parent=monitor, bevel=0.0)
box("mon_body", (0.55, 0.04, 0.34), (0, -0.02, 0.4), M["metal"], parent=monitor, bevel=0.01)
box("mon_screen", (0.51, 0.01, 0.30), (0, -0.045, 0.4), M["screen"], parent=monitor, bevel=0.0)
box("keyboard", (0.42, 0.14, 0.02), (DESK[0], DESK[1] + 0.05, DESK_Z + 0.01), M["metal"], bevel=0.004)
for i in range(3):
    box(f"papers{i}", (0.22, 0.3, 0.01), (DESK[0] + 0.42, DESK[1] + 0.05, DESK_Z + 0.005 + i * 0.012),
        material(f"paper{i}", (0.95, 0.95, 0.92)), bevel=0.0, rot=(0, 0, 0.1 * i))
plate = empty("plate", (DESK[0] + 0.15, DESK[1] - 0.2, DESK_Z))
box("plate_body", (0.26, 0.06, 0.07), (0, 0, 0.035), M["plate"], parent=plate, bevel=0.006)
text("plate_text", "課長", 0.06, (0, -0.031, 0.036), M["gold"], rot=(math.pi / 2, 0, 0), parent=plate)
rod("pot2", 0.12, 0.3, (2.85, 1.15, 0.15), M["pot"])
ball("plant2", 0.28, (2.85, 1.15, 0.6), M["plant"], scale=(1, 1, 1.4))

# 届いた箱（前の板が手前に倒れて開く）
BOX = (-0.75, -0.25)
crate = empty("crate", (*BOX, 0))
BW, BD, BH = 0.6, 0.55, 1.85
box("crate_back", (BW, 0.02, BH), (0, BD / 2, BH / 2), M["cardboard"], parent=crate, bevel=0.0)
for sx in (-1, 1):
    box(f"crate_side{sx}", (0.02, BD, BH), (sx * BW / 2, 0, BH / 2), M["cardboard"], parent=crate, bevel=0.0)
box("crate_top", (BW, BD, 0.02), (0, 0, BH), M["cardboard"], parent=crate, bevel=0.0)
box("crate_tape", (0.08, BD + 0.01, 0.025), (0, 0, BH), M["tape"], parent=crate, bevel=0.0)
flap = empty("crate_flap", (0, -BD / 2, 0), parent=crate)
box("crate_front", (BW, 0.02, BH), (0, 0, BH / 2), M["cardboard"], parent=flap, bevel=0.0)
box("crate_front_tape", (0.08, 0.025, BH), (0, -0.005, BH / 2), M["tape"], parent=flap, bevel=0.0)

# ---- 人形 --------------------------------------------------------------------

me = kit.Character("me", "casual_man.glb", "quaternius", 1.70)
clone = kit.Character("clone", "casual_man.glb", "quaternius", 1.70)
clone_desk = kit.Character("clone_desk", "casual_man.glb", "quaternius", 1.70)
wife = kit.Character("wife", "casual_woman.glb", "mixamo", 1.58)
wife.tint_texture(0.09, 0.2, 0.35, (0.05, 0.025, 0.015))
kit.seat(me, (SOFA[0], SOFA[1] - 0.12, 0), -math.pi / 2, seat_h=0.44)
FACE_ME = math.atan2(SOFA[1] - BOX[1], SOFA[0] - BOX[0])
kit.stand(clone, (*BOX, 0), FACE_ME)
kit.seat(clone_desk, (DESK[0], DESK[1] + 0.6, 0), -math.pi / 2)
kit.stand(wife, (DESK[0] + 0.85, DESK[1] + 0.25, 0), -math.pi / 2 - 0.4)
for c in (me, clone, clone_desk, wife):
    c.turn("spine", 1)
    c.turn("neck", 1)
HEAD = me.to_local(me.bone_world("head")).z


def phone(name, side):
    """スマホ。手のひらにのせる（kit.hold の X 軸が手のひらの向き：右手は -X、左手は +X）。"""
    root = empty(name)
    palm = -1 if side == "R" else 1
    # 長い辺を指の向き（Y）にして、手のひらの上にのせる。画面は手のひらと反対の側（顔のほう）
    box(f"{name}_body", (0.012, 0.16, 0.08), (palm * 0.035, 0.04, 0.0), M["phone"], parent=root, bevel=0.004)
    box(f"{name}_screen", (0.002, 0.14, 0.07), (palm * 0.042, 0.04, 0.0), M["phone_screen"], parent=root,
        bevel=0.0)
    return root


my_phone = phone("my_phone", "R")
desk_phone = phone("desk_phone", "L")


def hold_phone_front(c, side, frame):
    """スマホをおなかの前で見る（手のひらを上にして、スマホをのせる。カメラから画面の裏が見える）。"""
    s = 1 if side == "L" else -1
    c.reach(side, frame, local=(0.32, s * 0.02, HEAD - 0.52), fingers=(1, 0, 0.25), thumb=(0, s, 0))


def phone_to_ear(c, side, frame):
    s = 1 if side == "L" else -1
    c.reach(side, frame, local=(0.04, s * 0.15, HEAD - 0.08), fingers=(0.2, 0, 1), thumb=(-1, 0, 0))


hold_phone_front(me, "R", 1)
me.hold(my_phone, "R")
clone_desk.hold(desk_phone, "L")
kit.show(desk_phone, 1, False)

# ---- 段取り ------------------------------------------------------------------

# 出番
clone.show(1, False)
clone.show(F(S[1]["start"] + 0.2), True)       # 箱が開いたら見える
HIDE_CLONE = S[2]["end"] - 0.3
clone.show(F(HIDE_CLONE), False)
clone_desk.show(1, False)
clone_desk.show(F(HIDE_CLONE), True)
wife.show(1, False)
wife.show(F(S[12]["start"] - 0.3), True)
kit.show(plate, 1, False)
kit.show(plate, F(S[6]["start"] + 2.2), True)

# 箱が上から落ちてくる → 前の板が倒れる
interp("BEZIER")
DROP = S[0]["end"] - 1.6
crate.location.z = 3.2
crate.keyframe_insert("location", index=2, frame=1)
crate.keyframe_insert("location", index=2, frame=F(DROP))
crate.location.z = 0.0
crate.keyframe_insert("location", index=2, frame=F(DROP + 0.45))
kit.set_interp(crate, [F(DROP)], "LINEAR")
crate.location.z = 0.08
crate.keyframe_insert("location", index=2, frame=F(DROP + 0.6))
crate.location.z = 0.0
crate.keyframe_insert("location", index=2, frame=F(DROP + 0.75))
flap.keyframe_insert("rotation_euler", frame=F(S[1]["start"]))
flap.rotation_euler = (-math.pi / 2, 0, 0)
flap.keyframe_insert("rotation_euler", frame=F(S[1]["start"] + 0.45))
kit.show(crate, 1, True)
kit.show(crate, F(S[3]["start"] + 0.3), False)    # 片づけた

# 僕：スマホで注文 → 箱を見る → クローンに手をふる
me.turn("neck", F(0.5), pitch=0.4)
me.turn("neck", F(DROP + 0.4), pitch=0.3)
me.turn("neck", F(DROP + 0.8), pitch=0.0, yaw=-0.5)
me.touch("R", F(S[1]["start"] - 0.3), on=False)
me.turn("neck", F(S[2]["start"] + 0.5), yaw=-0.5)
# クローン：箱から出て、会社へ
clone.turn("neck", F(S[1]["start"] + 1.5))
clone.turn("neck", F(S[1]["start"] + 2.0), pitch=0.15)   # 会釈
clone.turn("spine", F(S[1]["start"] + 2.0), pitch=0.2)
clone.turn("neck", F(S[1]["start"] + 2.6))
clone.turn("spine", F(S[1]["start"] + 2.6))
kit.walk(clone, F, S[2]["start"] + 0.2, S[2]["end"] - 0.6, (0.9, -0.25), stride=0.6)
me.turn("neck", F(S[2]["end"]), yaw=-0.2)
# 会社のクローン：キーボードを打つ
KEYS = (DESK[0], DESK[1] + 0.05, DESK_Z + 0.04)


def typing(c, t0, t1):
    t = t0
    i = 0
    while t < t1:
        for side, dx in (("L", 0.09), ("R", -0.09)):
            up = 0.03 if (i + (side == "L")) % 2 else 0.0
            c.touch(side, F(t), (KEYS[0] + dx, KEYS[1] - 0.03, KEYS[2] + up), (KEYS[0] + dx * 0.5, KEYS[1] - 0.2,
                                                                                    KEYS[2]), on=True)
        t += 0.22
        i += 1


typing(clone_desk, HIDE_CLONE, S[3]["start"] + 0.5)
clone_desk.turn("neck", F(HIDE_CLONE), pitch=0.25, yaw=0.35)
# 僕はのんびり寝る（ソファにもたれる）＋ Z
me.turn("spine", F(S[3]["start"] + 0.2))
me.turn("spine", F(S[3]["start"] + 0.8), pitch=-0.4)
me.turn("neck", F(S[3]["start"] + 0.8), pitch=-0.25, roll=0.25)
me.touch("L", F(S[3]["start"] + 0.8), on=False)
zs = []
for i in range(3):
    z = text(f"zzz{i}", "Z", 0.16 + i * 0.06, (SOFA[0] + 0.2 + i * 0.2, SOFA[1] - 0.8, 1.2 + i * 0.22),
             M["zzz"], rot=(math.pi / 2, 0, 0.1))
    kit.show(z, 1, False)
    kit.show(z, F(S[3]["start"] + 1.0 + i * 0.4), True)
    kit.show(z, F(S[4]["start"] + 0.2), False)
# 給料が入ってくる（スマホの上に ¥）
me.turn("spine", F(S[4]["start"] + 0.2), pitch=-0.4)
me.turn("spine", F(S[4]["start"] + 0.8), pitch=-0.15)
me.turn("neck", F(S[4]["start"] + 0.8), pitch=0.3)
hold_phone_front(me, "R", F(S[4]["start"] + 0.8))
yen = text("yen", "￥", 0.3, (SOFA[0] - 0.38, SOFA[1] - 0.9, 1.25), M["yen"], rot=(math.pi / 2, 0, 0), extrude=0.01)
kit.show(yen, 1, False)
kit.show(yen, F(S[4]["start"] + 1.2), True)
kit.show(yen, F(S[5]["start"]), False)
me.turn("neck", F(S[4]["end"]), pitch=0.15, roll=-0.15)
me.touch("R", F(S[5]["start"] + 0.5), on=False)
# 会社：優秀なクローン → 課長
typing(clone_desk, S[5]["start"], S[6]["start"] + 2.0)
clone_desk.turn("neck", F(S[5]["start"]), pitch=0.25, yaw=0.35)
clone_desk.turn("spine", F(S[6]["start"] + 2.0))
clone_desk.turn("spine", F(S[6]["start"] + 2.6), pitch=-0.1)
clone_desk.turn("neck", F(S[6]["start"] + 2.6), pitch=-0.05)
clone_desk.touch("L", F(S[6]["start"] + 2.4), on=False)
clone_desk.touch("R", F(S[6]["start"] + 2.4), on=False)
# 夜：電話がかかってくる
NIGHT = S[7]["start"] - 0.2
for t in (S[7]["start"] + 1.0, S[7]["start"] + 1.4, S[7]["start"] + 1.8):   # スマホが鳴る（ふるえる光）
    kit.emission_socket(M["phone_screen"]).default_value = 0.6
    kit.emission_socket(M["phone_screen"]).keyframe_insert("default_value", frame=F(t))
    kit.emission_socket(M["phone_screen"]).default_value = 3.0
    kit.emission_socket(M["phone_screen"]).keyframe_insert("default_value", frame=F(t + 0.2))
kit.emission_socket(M["phone_screen"]).default_value = 0.6
kit.emission_socket(M["phone_screen"]).keyframe_insert("default_value", frame=F(S[7]["start"] + 2.3))
me.turn("spine", F(S[7]["start"] + 1.6))
me.turn("neck", F(S[7]["start"] + 1.6))
phone_to_ear(me, "R", F(S[7]["end"]))
kit.show(desk_phone, F(S[8]["start"] - 0.5), True)
phone_to_ear(clone_desk, "L", F(S[8]["start"]))
clone_desk.turn("spine", F(S[8]["start"]), pitch=-0.1)
for t in (S[8]["start"] + 0.6, S[8]["start"] + 2.0, S[8]["start"] + 3.4):
    clone_desk.turn("neck", F(t), pitch=0.1)
    clone_desk.turn("neck", F(t + 0.35), pitch=-0.05)
# 僕は笑う → 首をふる
t = S[9]["start"]
for i in range(4):
    me.turn("spine", F(t), pitch=-0.25 if i % 2 == 0 else -0.1)
    me.turn("neck", F(t), pitch=-0.25 if i % 2 == 0 else -0.05)
    t += 0.25
t = S[10]["start"] + 0.3
for i in range(5):
    me.turn("neck", F(t), yaw=0.25 if i % 2 == 0 else -0.25)
    t += 0.35
me.turn("neck", F(t))
me.turn("spine", F(t), pitch=0.0)
# 誰も反対しなかった → 妻がまっさきに手をあげる
me.turn("spine", F(S[11]["start"] + 1.0), pitch=0.15)
me.turn("neck", F(S[11]["start"] + 1.0), pitch=0.25)
wife.hang("R", F(S[12]["start"] + 0.6))
wife.reach("R", F(S[12]["start"] + 1.2), local=(0.08, -0.22, 1.75), fingers=(0, 0, 1), thumb=(-1, 0, 0))
wife.reach("R", F(DURATION), local=(0.08, -0.22, 1.78), fingers=(0, 0, 1), thumb=(-1, 0, 0))
wife.turn("neck", F(S[12]["start"] + 1.2), roll=-0.15)
clone_desk.turn("neck", F(S[12]["start"] + 1.0), yaw=-0.6)
me.touch("R", F(S[12]["start"] + 1.6), on=False)          # スマホを下ろす
me.turn("neck", F(S[12]["start"] + 1.6), pitch=0.35)

# ---- 光（昼 → 夜） -------------------------------------------------------------

lamp_home = light("lamp_home", "POINT", (-1.6, 0.2, 2.2), 120, (1.0, 0.82, 0.62), size=0.3)
lamp_office = light("lamp_office", "AREA", (1.6, 0.3, 2.4), 220, (0.92, 0.96, 1.0), size=1.2, target=(1.6, 0.3, 0))
fill = light("fill", "AREA", (0.0, -4.5, 3.5), 380, (1.0, 0.95, 0.9), size=5.0, target=(0, 0.3, 0.9))
win_light = [light(f"win_light{x}", "AREA", (x, BACK_Y - 0.15, 1.5), 60, (0.7, 0.85, 1.0), size=1.0,
                   target=(x, 0, 0.8)) for x in (-1.6, 1.6)]
win_sock = kit.emission_socket(M["window"])
win_col = M["window"].node_tree.nodes.get("Principled BSDF").inputs["Emission Color"]


def lights(frame, day):
    fill.data.energy = 380 if day else 120
    lamp_home.data.energy = 120 if day else 160
    lamp_office.data.energy = 220 if day else 160
    for w in win_light:
        w.data.energy = 60 if day else 0
        w.data.keyframe_insert("energy", frame=frame)
    win_sock.default_value = 1.2 if day else 0.25
    win_col.default_value = (0.55, 0.75, 1.0, 1) if day else (0.1, 0.15, 0.4, 1)
    for d, p in ((fill.data, "energy"), (lamp_home.data, "energy"), (lamp_office.data, "energy")):
        d.keyframe_insert(p, frame=frame)
    win_sock.keyframe_insert("default_value", frame=frame)
    win_col.keyframe_insert("default_value", frame=frame)


lights(1, True)
lights(F(NIGHT), False)
for id_ in (fill.data, lamp_home.data, lamp_office.data, *[w.data for w in win_light]):
    kit.make_constant(id_)

# ---- カメラ ------------------------------------------------------------------

target = empty("cam_target", (0, 0, 1))
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
    "wide":    ((0.0, -8.6, 4.4), (0.0, 0.3, 0.9)),
    "home":    ((-0.9, -4.6, 2.3), (-1.3, 0.3, 0.9)),
    "sofa":    ((-1.2, -2.2, 1.35), (-1.55, 0.6, 1.0)),
    "crate":   ((-0.4, -2.9, 1.5), (-1.1, 0.2, 1.0)),
    "two":     ((-1.0, -2.6, 1.55), (-1.15, 0.25, 1.1)),
    "door":    ((-0.6, -3.6, 1.8), (0.3, -0.2, 1.0)),
    "office":  ((1.2, -2.6, 1.6), (1.55, 0.6, 1.0)),
    "desk":    ((1.15, -1.3, 1.25), (1.55, 0.65, 1.05)),
    "plate":   ((1.55, -0.75, 0.95), (DESK[0] + 0.15, DESK[1] - 0.2, DESK_Z + 0.06)),
    "night":   ((0.0, -7.6, 3.8), (0.0, 0.3, 1.0)),
    "office_wife": ((1.0, -2.9, 1.7), (1.9, 0.6, 1.2)),
}
CUTS = [
    (0.0, "home"), (S[0]["end"] - 2.2, "home"), (S[0]["end"], "crate"),
    (S[1]["start"] + 0.6, "two"), (S[1]["end"], "two"),
    (S[2]["start"] + 0.4, "door"), (HIDE_CLONE - 0.05, "door"),
    (HIDE_CLONE, "office"), (S[3]["start"], "sofa"), (S[4]["end"], "sofa"),
    (S[5]["start"], "desk"), (S[6]["start"] + 1.5, "desk"), (S[6]["start"] + 2.4, "plate"), (S[6]["end"], "plate"),
    (S[7]["start"], "sofa"), (S[7]["end"], "sofa"),
    (S[8]["start"], "night"), (S[8]["end"], "night"),
    (S[9]["start"], "sofa"), (S[10]["end"], "sofa"),
    (S[11]["start"], "wide"), (S[11]["end"], "wide"),
    (S[12]["start"], "office_wife"), (S[12]["end"] - 1.2, "office_wife"), (DURATION, "wide"),
]
CUT_HARD = {HIDE_CLONE, S[3]["start"], S[5]["start"], S[7]["start"], S[8]["start"], S[9]["start"],
            S[11]["start"], S[12]["start"]}
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
