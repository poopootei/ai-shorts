"""3D の背景で動画を作る（試作）。Blender で舞台を書き出し、声・字幕・クレジットと合わせる。

    python scripts/render_3d.py -c shortshort 20261124-002                    # 全部書き出して合成
    python scripts/render_3d.py -c shortshort 20261124-002 --stills 1,21,39   # 下見：その秒のコマだけ PNG
    python scripts/render_3d.py -c shortshort 20261124-002 --compose-only     # コマはそのまま、合成だけやり直す
    python scripts/render_3d.py -c shortshort 20261124-002 --adopt            # 3D 版を video.mp4 にする（このあと qa）

入力：work/{id}/timing.json、mix.wav（render で作った声 + BGM）、subs.ass、
      舞台のスクリプト scripts/blender/{id}.py
出力：work/{id}/3d/frames/####.jpg → work/{id}/video_3d.mp4
      （今の video.mp4 は上書きしない。動画CHECK の前に見比べるため）
採用：--adopt で video_3d.mp4 を video.mp4 にする。前の video.mp4 は video_static.mp4 に残し、
      work/{id}/visual.json（説明文の「映像：」のクレジット）を書く。続けて qa → 動画CHECK → approve-video。
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ai_shorts.config import add_channel_arg, script_root  # noqa: E402

ROOT = script_root()

from ai_shorts import ffmpeg  # noqa: E402
from ai_shorts.config import load_project  # noqa: E402
from ai_shorts.errors import AiShortsError, ExternalToolError  # noqa: E402
from ai_shorts.render import credit_filter, rel_to_root, subs_filter  # noqa: E402

SCENES = Path(__file__).resolve().parent / "blender"


def blender(project, story_id: str, work: Path, out: Path, stills: str, scale: int,
            exe_arg: str | None) -> None:
    exe = Path(exe_arg or project.get("blender.exe", "blender"))
    if not exe.exists():
        raise ExternalToolError(f"Blender が見つかりません: {exe}（config の blender.exe を直してください）")
    scene = SCENES / f"{story_id}.py"
    if not scene.exists():
        raise AiShortsError(f"舞台のスクリプトがありません: {scene}")
    cmd = [str(exe), "-b", "--factory-startup", "-P", str(scene), "--",
           "--timing", str(work / "timing.json"), "--out", str(out),
           "--fps", str(project.get("render.fps")),
           "--width", str(project.get("render.width")), "--height", str(project.get("render.height")),
           "--samples", str(project.get("blender.samples", 16)), "--scale", str(scale)]
    if stills:
        cmd += ["--stills", stills]
    log = out / "blender.log"
    out.mkdir(parents=True, exist_ok=True)
    print(f"[3d] Blender: {scene.name}（ログ: {log}）")
    with log.open("w", encoding="utf-8", errors="replace") as f:
        proc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
    if proc.returncode != 0:
        tail = "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-15:])
        raise ExternalToolError(f"Blender が失敗しました（終了コード {proc.returncode}）:\n{tail}")


def compose(project, work: Path, out: Path) -> Path:
    frames = out / "frames"
    if not (frames / "0001.jpg").exists():
        raise AiShortsError(f"{frames} にコマがありません。先に Blender で書き出してください。")
    audio = work / "mix.wav"
    if not audio.exists():
        raise AiShortsError(f"{audio} がありません。先に render を実行してください。")
    duration = ffmpeg.duration(audio)
    if duration > float(project.get("render.max_video_seconds")):
        raise AiShortsError(f"音声が {duration:.2f} 秒で、上限を超えています。")

    def rel(p: Path) -> str:
        return rel_to_root(project, p)

    tail = [s for s in (subs_filter(project, work), credit_filter(project, work)) if s]
    video = work / "video_3d.mp4"
    fps = str(project.get("render.fps"))
    ffmpeg.run(
        [
            "-framerate", fps, "-i", rel(frames / "%04d.jpg"),
            "-i", rel(audio),
            "-vf", ",".join([*tail, "format=yuv420p"]),
            "-map", "0:v", "-map", "1:a",
            "-t", f"{duration:.3f}", "-r", fps,
            "-c:v", "libx264", "-preset", str(project.get("render.x264_preset", "medium")),
            "-crf", str(project.get("render.crf", 20)), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            rel(video),
        ],
        cwd=project.root,
    )
    print(f"[3d] → {video}（{ffmpeg.duration(video):.2f} 秒）")
    return video


QUATERNIUS = ("casual_man.glb", "casual_woman.glb")   # クレジットに名前を出す人形（CC0。assets/3d/characters/SOURCES.md）


def credit_for(project, story_id: str) -> str:
    """説明文の「映像：」。舞台が Quaternius の人形を使っていれば blender.credit、自前の人形だけなら blender.credit_own。"""
    scene = SCENES / f"{story_id}.py"
    text = scene.read_text(encoding="utf-8") if scene.exists() else ""
    if any(f in text for f in QUATERNIUS):
        return project.get("blender.credit", "3D（Blender）、人形：Quaternius（CC0）")
    return project.get("blender.credit_own", "3D（Blender）")


def adopt(project, work: Path, story_id: str) -> Path:
    """3D 版を本番の video.mp4 にする。静止画の版は video_static.mp4 に残す（一度だけ）。"""
    src = work / "video_3d.mp4"
    if not src.exists():
        raise AiShortsError(f"{src} がありません。先に書き出してください。")
    video, static = work / "video.mp4", work / "video_static.mp4"
    if video.exists() and not static.exists():
        video.replace(static)
        print(f"[3d] 静止画の版 → {static}")
    shutil.copy2(src, video)
    credit = credit_for(project, story_id)
    (work / "visual.json").write_text(
        json.dumps({"kind": "3d", "credit": credit}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[3d] 採用 → {video}（続けて qa を実行してください）")
    return video


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_channel_arg(ap)
    ap.add_argument("story_id")
    ap.add_argument("--stills", default="", help="この秒のコマだけ PNG で書き出す（カンマ区切り）")
    ap.add_argument("--scale", type=int, default=100, help="解像度の %%（下見は 50）")
    ap.add_argument("--compose-only", action="store_true", help="Blender を動かさず、合成だけやり直す")
    ap.add_argument("--blender", help="blender.exe の場所（config の blender.exe より優先）")
    ap.add_argument("--adopt", action="store_true", help="書き出し済みの video_3d.mp4 を video.mp4 にする（このあと qa）")
    a = ap.parse_args()

    project = load_project(ROOT)
    work = project.root / "work" / a.story_id
    if not (work / "timing.json").exists():
        print(f"エラー: {work / 'timing.json'} がありません。先に tts を実行してください。")
        return 1
    out = work / "3d"
    try:
        if a.adopt:
            adopt(project, work, a.story_id)
            return 0
        if not a.compose_only:
            blender(project, a.story_id, work, out, a.stills, a.scale, a.blender)
        if not a.stills:
            compose(project, work, out)
    except AiShortsError as e:
        print(f"エラー: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
