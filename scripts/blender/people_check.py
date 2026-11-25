"""自前の人形の下見（物語なし）。座る・立つ・手を伸ばす・歩く・表情・口パク・Mixamo の動きを1つの舞台で確かめる。
人形を作り直したとき、足したときに使う（make_characters.py のあと）。

    D:\\blender\\blender.exe -b --factory-startup -P scripts/blender/people_check.py -- --out DIR [--stills 1,3,5] [--scale 50]

出力：DIR/still_{秒}.png。ひじ・ひざの曲がる向き（IK の pole）は、数値でも表に出す（POLES の行）。
"""

from __future__ import annotations

import argparse
import math
import sys
import types
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).parent))
import kit  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--stills", default="0.5,2.5,4.5,6.5")
ap.add_argument("--scale", type=int, default=50)
ap.add_argument("--clip", default="sitting_idle", help="座った人形に重ねる Mixamo の動き（なければ使わない）")
a = ap.parse_args(argv)
args = types.SimpleNamespace(samples=16, width=1080, height=1920, scale=a.scale, fps=30, stills=a.stills, out=a.out)
DURATION = 8.0


def F(t):
    return int(round(t * args.fps)) + 1


scene = kit.setup_scene(args, DURATION, world_color=(0.05, 0.06, 0.09))

M = {
    "floor": kit.material("floor", (0.32, 0.28, 0.24), rough=0.8),
    "wall": kit.material("wall", (0.55, 0.52, 0.48), rough=0.9),
    "wood": kit.wood("wood", (0.20, 0.11, 0.05), (0.35, 0.21, 0.10)),
    "chair": kit.material("chair", (0.30, 0.18, 0.10), rough=0.6),
    "cup": kit.material("cup", (0.85, 0.85, 0.82), rough=0.3),
}
kit.box("floor", (8, 8, 0.1), (0, 0, -0.05), M["floor"], bevel=0)
kit.box("wall", (8, 0.1, 4), (0, 2.2, 2), M["wall"], bevel=0)
kit.table("table", (0, 0.6), (1.1, 0.7), 0.72, M["wood"])
cup = kit.rod("cup", 0.04, 0.09, (0.25, 0.45, 0.765), M["cup"])

# 4人：若い男と年配の女が座り、若い女が立って手を伸ばし、年配の男が歩いてくる
ym = kit.person("young_man")
ow = kit.person("old_woman")
yw = kit.person("young_woman")
om = kit.person("old_man")
kit.chair("c1", (-0.8, 0.6, 0), 0.0, M["chair"])
kit.chair("c2", (0.8, 0.6, 0), math.pi, M["chair"])
use_clip = (kit.MOTIONS / f"{a.clip}.fbx").exists()
kit.seat(ym, (-0.78, 0.6, 0), 0.0, arms="clip" if use_clip else "ik")
kit.seat(ow, (0.78, 0.6, 0), math.pi)
kit.stand(yw, (0.0, -0.05, 0), math.pi / 2)
kit.stand(om, (-1.6, -0.6, 0), 0.0)

# 動き
yw.reach("R", F(1.5), world=(0.25, 0.38, 0.80), fingers=(1, 0, -0.3), thumb=(0, 0, 1))   # カップへ手を伸ばす
yw.hang("R", F(4.0))
yw.turn("neck", F(1.5), pitch=0.35)
yw.turn("neck", F(4.0), pitch=0.0)
ow.touch("L", F(2.0), wrist_world=(0.45, 0.62, 0.74), fingers_world=(0.2, 0.62, 0.74))
kit.walk(om, F, 3.0, 6.0, (-0.6, -0.5))
if use_clip:
    ym.play(a.clip, 1, F(DURATION), amount=0.6)
    ym.turn("neck", F(2.0), yaw=-0.4)
    ym.bake(F(DURATION))

# 表情
for c in (ym, ow, yw, om):
    c.blinks(1, F(DURATION))
yw.expr(F(1.0), smile=1)
ym.talk(F(0.5), F(2.8))
ym.expr(F(4.0), surprise=1)
ow.expr(F(2.0), smile=1)
ow.expr(F(4.5), smile=0, sad=1)
om.expr(F(6.0), angry=1)

# 光とカメラ
kit.light("key", "AREA", (-2, -3, 3.2), 380, (1.0, 0.95, 0.88), size=2.5, target=(0, 0.4, 0.9))
kit.light("fill", "AREA", (2.5, -2.5, 2.0), 150, (0.85, 0.9, 1.0), size=3, target=(0, 0.4, 0.9))
kit.light("top", "POINT", (0, 0.6, 2.6), 120, (1.0, 0.9, 0.8))
cd = bpy.data.cameras.new("cam")
cd.lens = 32
cam = bpy.data.objects.new("cam", cd)
kit.col().objects.link(cam)
cam.location = (0.1, -3.9, 1.65)
kit.aim(cam, (-0.2, 0.3, 0.85))
scene.camera = cam

# ひじ・ひざの向き（数値）：ひじは後ろ（f<0）・外、ひざは前（f>0）なら正しい
scene.frame_set(1)
for c in (ym, ow, yw, om):
    out = []
    for S, side, out_sign in (("Left", "L", 1), ("Right", "R", -1)):
        def j(b):
            return c.to_local(c.arm.matrix_world @ c.arm.pose.bones[b].head)

        def perp(p0, p1, m):
            d = (p1 - p0).normalized()
            v = m - p0
            return v - d * v.dot(d)
        e = perp(j(f"{S}Arm"), j(f"{S}Hand"), j(f"{S}ForeArm"))
        k = perp(j(f"{S}UpLeg"), j(f"{S}Foot"), j(f"{S}Leg"))
        out.append(f"{side} ひじ 前{e.x:+.2f} 外{e.y * out_sign:+.2f} / ひざ 前{k.x:+.2f}")
    print(f"POLES {c.name}: " + " | ".join(out))

kit.render(args, scene, F)
