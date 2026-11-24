"""「嘘発見器」（20261124-002）の 3D の舞台（試作）。Blender の中で動かす（scripts/render_3d.py から）。

断面の部屋（床と壁2枚）に、テーブル・嘘発見器の箱・椅子と夫婦の人形を置く。
人形は assets/3d/characters/ の glb（Quaternius、CC0）。手足は IK の行き先で動かす（kit.py）。
動き（カメラ・ランプ・しぐさ）は timing.json の文の時刻に合わせる。
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
import kit  # noqa: E402
from kit import ball, box, cone, empty, interp, light, material, rod, wood  # noqa: E402

args = kit.parse_args()
tl = kit.Timeline(args.timing, args.fps)
S, F, DURATION = tl.S, tl.F, tl.duration
scene = kit.setup_scene(args, DURATION)

# ---- 材質 --------------------------------------------------------------------

M = {
    "floor": wood("floor", (0.20, 0.10, 0.04), (0.42, 0.24, 0.11)),
    "table": wood("table", (0.28, 0.15, 0.07), (0.52, 0.32, 0.16), stretch=(1.0, 10.0, 1.0)),
    "boxwood": wood("boxwood", (0.10, 0.05, 0.02), (0.22, 0.12, 0.05), stretch=(1.0, 30.0, 1.0)),
    "wall": material("wall", (0.78, 0.70, 0.58), rough=0.9),
    "wall_cut": material("wall_cut", (0.30, 0.27, 0.24), rough=0.9),
    "rug": material("rug", (0.16, 0.30, 0.24), rough=1.0),
    "window": material("window", (0.02, 0.04, 0.10), emission=(0.10, 0.18, 0.45), strength=1.5),
    "frame": material("frame", (0.90, 0.88, 0.82), rough=0.5),
    "chair": material("chair", (0.55, 0.40, 0.26), rough=0.5),
    "metal": material("metal", (0.08, 0.08, 0.08), rough=0.35),
    "shade": material("shade", (0.95, 0.85, 0.65), rough=0.6, emission=(1.0, 0.75, 0.45), strength=2.0),
    "plant": material("plant", (0.10, 0.32, 0.12), rough=0.8),
    "pot": material("pot", (0.65, 0.35, 0.22), rough=0.7),
    "lamp_red": material("lamp_red", (0.35, 0.02, 0.02), rough=0.3, emission=(1.0, 0.05, 0.03)),
    "lamp_blue": material("lamp_blue", (0.01, 0.03, 0.4), rough=0.3, emission=(0.0, 0.06, 1.0)),
}

# ---- 部屋 --------------------------------------------------------------------

box("floor", (4.4, 4.4, 0.2), (0, 0, -0.1), M["floor"], bevel=0.0)
box("floor_cut", (4.42, 4.42, 0.12), (0, 0, -0.27), M["wall_cut"], bevel=0.0)
box("wall_back", (4.4, 0.2, 2.8), (0, 2.3, 1.4), M["wall"], bevel=0.0)
box("wall_left", (0.2, 4.6, 2.8), (-2.3, 0.1, 1.4), M["wall"], bevel=0.0)
box("wall_back_top", (4.42, 0.22, 0.04), (0, 2.3, 2.82), M["wall_cut"], bevel=0.0)
box("wall_left_top", (0.22, 4.62, 0.04), (-2.3, 0.1, 2.82), M["wall_cut"], bevel=0.0)
box("baseboard_b", (4.4, 0.03, 0.1), (0, 2.185, 0.05), M["frame"], bevel=0.0)
box("baseboard_l", (0.03, 4.4, 0.1), (-2.185, 0.1, 0.05), M["frame"], bevel=0.0)
box("window_frame", (1.3, 0.06, 1.5), (0.7, 2.19, 1.55), M["frame"], bevel=0.01)
box("window", (1.16, 0.06, 1.36), (0.7, 2.17, 1.55), M["window"], bevel=0.0)
box("window_bar", (0.04, 0.07, 1.36), (0.7, 2.16, 1.55), M["frame"], bevel=0.0)
box("picture_frame", (0.04, 0.7, 0.5), (-2.18, -0.3, 1.6), M["frame"], bevel=0.008)
box("picture", (0.04, 0.6, 0.4), (-2.17, -0.3, 1.6), material("picture", (0.55, 0.42, 0.25), rough=0.9), bevel=0.0)
box("sideboard", (1.2, 0.4, 0.7), (-1.3, 1.95, 0.35), M["table"], bevel=0.015)
rod("pot", 0.12, 0.22, (-1.0, 1.95, 0.81), M["pot"])
ball("plant", 0.2, (-1.0, 1.95, 1.05), M["plant"], scale=(1, 1, 1.25))
rod("rug", 1.3, 0.015, (0, 0, 0.008), M["rug"])

TABLE_TOP = 0.725
kit.table("table", (0, 0), (0.78, 0.7), TABLE_TOP, M["table"])
rod("lamp_cord", 0.006, 0.8, (0, 0, 2.4), M["metal"])
cone("lamp_shade", 0.28, 0.06, 0.22, (0, 0, 1.95), M["shade"])

# 嘘発見器
BOX_TOP = TABLE_TOP + 0.09
# ランプは手前（カメラ側）の縁に横に並べ、手は奥の半分にのせる（手でランプが隠れないように）
LAMP_Y = -0.045
RED_AT, BLUE_AT = (-0.035, LAMP_Y, BOX_TOP), (0.035, LAMP_Y, BOX_TOP)
box("detector", (0.24, 0.16, 0.09), (0, 0, TABLE_TOP + 0.045), M["boxwood"], bevel=0.008)
ball("lamp_red", 0.022, RED_AT, M["lamp_red"], scale=(1, 1, 0.8))
ball("lamp_blue", 0.022, BLUE_AT, M["lamp_blue"], scale=(1, 1, 0.8))
box("detector_grill", (0.15, 0.012, 0.04), (0, -0.081, TABLE_TOP + 0.045), M["metal"], bevel=0.0)

# ---- 人形 --------------------------------------------------------------------

SEAT_X = 0.64
kit.chair("wife_chair", (-SEAT_X, 0, 0), 0.0, M["chair"])
kit.chair("husband_chair", (SEAT_X, 0, 0), math.pi, M["chair"])
wife = kit.Character("wife", "casual_woman.glb", "mixamo", 1.58)
husband = kit.Character("husband", "casual_man.glb", "quaternius", 1.70)
wife.tint_texture(0.09, 0.2, 0.35, (0.05, 0.025, 0.015))     # 金髪 → こげ茶の髪
husband.recolor("Skin", (0.62, 0.45, 0.32))
# 腕と胴は Mixamo の動き（assets/3d/motions/mixamo/）に任せ、箱にふれるときだけ IK で手を置く
kit.seat(wife, (-SEAT_X + 0.02, 0, 0), 0.0, arms="clip")
kit.seat(husband, (SEAT_X - 0.02, 0, 0), math.pi, arms="clip")
# カメラ側（世界の -Y）の手で箱にふれる。妻は +X 向きなので右手、夫は -X 向きなので左手
WIFE_HAND, HUS_HAND = "R", "L"


def box_touch(side_x: float):
    """箱の上に手をのせる：手首は自分の側の縁の上、指先は箱の奥の半分を通して向こうへ、手のひらを下に。"""
    wrist = (side_x * 0.15, 0.05, BOX_TOP + 0.03)
    fingers = (side_x * -0.05, 0.055, BOX_TOP + 0.02)
    return wrist, fingers


# ---- 光 ----------------------------------------------------------------------

light("pendant", "POINT", (0, 0, 1.88), 90, (1.0, 0.78, 0.55), size=0.12)
light("fill", "AREA", (3.5, -3.5, 4.0), 260, (1.0, 0.9, 0.78), size=3.0, target=(0, 0, 0.8))
# 夫は -X を向いているので、夫の正面（-X 側の手前）からも柔らかく当てる
light("fill_husband", "AREA", (-2.0, -2.6, 2.6), 160, (1.0, 0.9, 0.8), size=2.0, target=(SEAT_X, 0, 0.95))
light("window_light", "AREA", (0.7, 2.0, 1.55), 30, (0.4, 0.55, 1.0), size=1.2, target=(0.7, 0, 0.8))
red_glow = light("red_glow", "POINT", (RED_AT[0], LAMP_Y, BOX_TOP + 0.06), 0, (1.0, 0.08, 0.05), size=0.03)
blue_glow = light("blue_glow", "POINT", (BLUE_AT[0], LAMP_Y, BOX_TOP + 0.10), 0, (0.02, 0.1, 1.0), size=0.03)
alarm = light("alarm", "POINT", (0, 0, 2.3), 0, (1.0, 0.06, 0.04), size=0.5)

# ---- 動き：ランプ ----------------------------------------------------------------


def lamp(mat, glow, on_strength, glow_energy, t0, t1, blink=None):
    """t0〜t1 のあいだランプをつける。blink（秒）を指定すると点滅。"""
    sock = kit.emission_socket(mat)

    def set_(t, on):
        sock.default_value = on_strength if on else 0.0
        sock.keyframe_insert("default_value", frame=F(t))
        glow.data.energy = glow_energy if on else 0.0
        glow.data.keyframe_insert("energy", frame=F(t))

    t, on = t0, True
    while t < t1:
        set_(t, on)
        if not blink:
            break
        t += blink
        on = not on
    set_(t1, False)


def alarm_light(t0, t1, period=0.25, energy=500):
    t, on = t0, True
    while t < t1:
        alarm.data.energy = energy if on else 0.0
        alarm.data.keyframe_insert("energy", frame=F(t))
        t += period
        on = not on
    alarm.data.energy = 0.0
    alarm.data.keyframe_insert("energy", frame=F(t1))


# 青は明るくしすぎると色調補正（AgX）で白っぽくなるので、発光は弱め（赤の 1/10 ほど）
for m_, g_ in ((M["lamp_red"], red_glow), (M["lamp_blue"], blue_glow)):
    s_ = kit.emission_socket(m_)
    s_.default_value = 0.0
    s_.keyframe_insert("default_value", frame=1)
    g_.data.energy = 0.0
    g_.data.keyframe_insert("energy", frame=1)
alarm.data.energy = 0.0
alarm.data.keyframe_insert("energy", frame=1)

lamp(M["lamp_red"], red_glow, 25, 25, S[2]["start"] + 1.0, S[2]["end"] - 0.3, blink=0.3)   # 説明の点滅
lamp(M["lamp_blue"], blue_glow, 1.0, 3, S[6]["start"], S[7]["start"])                      # 青が光った
lamp(M["lamp_blue"], blue_glow, 1.0, 3, S[8]["start"] + 0.9, S[9]["start"])                # また青だった
BUZZ1 = (S[13]["start"] - 0.3, S[14]["start"] - 0.2)      # もちろん → ブザー
BUZZ2 = (S[16]["start"] + 0.9, DURATION)                  # その言葉にも、ブザーは鳴った
for b0, b1 in (BUZZ1, BUZZ2):
    lamp(M["lamp_red"], red_glow, 40, 60, b0, b1, blink=0.25)
    alarm_light(b0, b1)

# ---- 動き：人形 ----------------------------------------------------------------


def still(c, t):
    """胴・首を元の姿勢に戻すキー。"""
    c.turn("spine", F(t))
    c.turn("neck", F(t))


for c in (wife, husband):
    still(c, 0)
    c.play("sitting_idle", 1, F(DURATION))          # ふだん：座って息をしている


def act(c, name, t0, t1, **kw):
    """t0〜t1 秒に Mixamo の動きを重ねる（出入りは 0.3 秒でなめらかに）。"""
    c.play(name, F(t0), F(t1), blend=9, **kw)


# Mixamo の動き（物語の文の時刻に合わせる）
act(wife, "sitting_laughing", S[3]["start"] - 0.2, S[3]["end"] + 0.3)          # 妻はずいぶん楽しそうだ
act(wife, "sitting_talking", S[4]["start"] - 0.2, S[4]["end"] + 0.4)           # 「あなた、浮気してない？」
act(husband, "sitting_rubbing_arm", S[4]["start"], S[5]["start"] + 0.4)        # 聞かれて落ち着かない
act(wife, "sitting_impatient", S[9]["start"], S[10]["end"])                    # つまらなそうに
act(husband, "sitting_talking", S[11]["start"] - 0.2, S[11]["end"] + 0.3)      # 「君は、僕のことを愛してる？」
act(wife, "sitting_laughing", S[12]["start"], S[12]["end"] + 0.3)              # にっこり笑って
act(husband, "disbelief_back", BUZZ1[0], BUZZ1[1] + 0.5, loop=False, amount=0.55)   # ブザー：のけぞる
act(wife, "disbelief_forward", S[14]["start"], DURATION, loop=False, amount=0.45)  # 箱を見つめる
act(husband, "scared", BUZZ2[0] - 0.2, DURATION, loop=False, move=0.35)        # 2度目のブザー：飛び上がる

# 妻が聞く：「あなた、浮気してない？」で身を乗り出す
wife.turn("spine", F(S[4]["start"] - 0.3))
wife.turn("spine", F(S[4]["start"] + 0.3), pitch=0.25)
# 夫が箱に手をのせる
w, f = box_touch(+1)
husband.touch(HUS_HAND, F(S[5]["start"] + 0.2), on=False)
husband.turn("spine", F(S[5]["start"] + 0.2))
husband.touch(HUS_HAND, F(S[5]["start"] + 1.0), w, f, on=True)
husband.turn("spine", F(S[5]["start"] + 1.0), pitch=0.3)
husband.touch(HUS_HAND, F(S[9]["start"]), w, f, on=True)
husband.turn("spine", F(S[9]["start"]), pitch=0.3)
husband.touch(HUS_HAND, F(S[9]["start"] + 0.7), on=False)
husband.turn("spine", F(S[9]["start"] + 0.7))
# 妻は、つまらなそうに（そっぽを向いて、のけぞる）
wife.turn("spine", F(S[9]["start"]), pitch=0.25)
wife.turn("neck", F(S[9]["start"]))
wife.turn("spine", F(S[9]["start"] + 0.7), pitch=-0.12)
wife.turn("neck", F(S[9]["start"] + 0.7), yaw=0.6, pitch=-0.1)
wife.turn("spine", F(S[10]["start"]), pitch=-0.12)
wife.turn("neck", F(S[10]["start"]), yaw=0.6, pitch=-0.1)
wife.turn("spine", F(S[10]["start"] + 0.8))
wife.turn("neck", F(S[10]["start"] + 0.8))
# 夫が聞く：「君は、僕のことを愛してる？」
husband.turn("spine", F(S[11]["start"] - 0.2))
husband.turn("spine", F(S[11]["start"] + 0.5), pitch=0.22)
# 妻が箱に手をのせて、にっこり
w, f = box_touch(-1)
wife.touch(WIFE_HAND, F(S[11]["end"] - 0.6), on=False)
wife.turn("spine", F(S[11]["end"] - 0.6))
wife.touch(WIFE_HAND, F(S[11]["end"] + 0.3), w, f, on=True)
wife.turn("spine", F(S[11]["end"] + 0.3), pitch=0.3)
# ブザーで夫が身を引く（前かがみをやめる。のけぞりは Mixamo の動き）
husband.turn("spine", F(BUZZ1[0]), pitch=0.22)
husband.turn("spine", F(BUZZ1[0] + 0.4))
# 妻は箱を見つめて、首をかしげる（見つめるのは Mixamo の動き、かしげるのはここで重ねる）
wife.turn("neck", F(S[14]["start"] + 1.6))
wife.turn("neck", F(S[14]["start"] + 2.2), roll=0.35)
wife.turn("neck", F(DURATION), roll=0.35)
wife.touch(WIFE_HAND, F(DURATION), w, f, on=True)

for c in (wife, husband):
    c.bake(F(DURATION))

# ---- カメラ ------------------------------------------------------------------

rig = empty("cam_rig")
target = empty("cam_target", (0, 0, 0.9))
cam_data = bpy.data.cameras.new("cam")
cam_data.lens = 32
cam_data.dof.use_dof = True
cam_data.dof.focus_object = target
cam_data.dof.aperture_fstop = 4.0
cam = bpy.data.objects.new("cam", cam_data)
kit.col().objects.link(cam)
cam.parent = rig
scene.camera = cam
c = cam.constraints.new("TRACK_TO")
c.target = target
c.track_axis = "TRACK_NEGATIVE_Z"
c.up_axis = "UP_Y"

SHOTS = {
    "wide":      ((4.6, -6.0, 3.9), (-0.25, 0.3, 0.95)),
    "wide_in":   ((3.9, -5.1, 3.3), (-0.2, 0.2, 0.92)),
    "box":       ((0.85, -1.25, 1.35), (0.0, 0.0, 0.8)),
    "box_in":    ((0.65, -1.0, 1.22), (0.0, 0.0, 0.8)),
    "table":     ((2.3, -3.1, 2.15), (0.0, 0.0, 0.9)),
    "wife":      ((1.0, -2.0, 1.35), (-0.55, 0.0, 1.0)),
    "husband":   ((-1.0, -2.0, 1.35), (0.55, 0.0, 1.0)),
    "wife_box":  ((0.8, -1.7, 1.3), (-0.3, 0.0, 0.95)),
    "final":     ((5.2, -6.8, 4.4), (-0.25, 0.3, 0.95)),
}
CUTS = [   # (秒, ショット)。間はなめらかに動く
    (0.0, "wide"), (S[1]["start"] - 0.3, "wide_in"),
    (S[1]["start"] + 1.4, "box"), (S[3]["start"] - 0.2, "box_in"),
    (S[4]["start"] - 0.4, "table"), (S[6]["start"] - 0.6, "table"),
    (S[6]["start"] + 0.2, "box"), (S[9]["start"] - 0.2, "box_in"),
    (S[9]["start"] + 0.8, "wife"), (S[10]["start"], "wife"),
    (S[10]["start"] + 1.0, "husband"), (S[11]["end"], "husband"),
    (S[12]["start"] + 0.4, "wife"), (BUZZ1[0], "wife"),
    (BUZZ1[0] + 0.6, "table"), (S[14]["start"], "table"),
    (S[14]["start"] + 1.0, "wife_box"), (BUZZ2[0], "wife_box"),
    (DURATION, "final"),
]
interp("BEZIER")
for t, name in CUTS:
    loc, tgt = SHOTS[name]
    cam.location = loc
    cam.keyframe_insert("location", frame=F(t))
    target.location = tgt
    target.keyframe_insert("location", frame=F(t))

# ブザーのあいだ、カメラを小さく揺らす
rng = random.Random(7)
rig.keyframe_insert("location", frame=1)
for b0, b1 in (BUZZ1, BUZZ2):
    t = b0
    while t < b1:
        rig.location = (rng.uniform(-1, 1) * 0.012, 0, rng.uniform(-1, 1) * 0.012)
        rig.keyframe_insert("location", frame=F(t))
        t += 2 / args.fps
    rig.location = (0, 0, 0)
    rig.keyframe_insert("location", frame=F(b1))

for id_ in (red_glow.data, blue_glow.data, alarm.data, rig,
            M["lamp_red"].node_tree, M["lamp_blue"].node_tree):
    kit.make_constant(id_)

kit.render(args, scene, F)
