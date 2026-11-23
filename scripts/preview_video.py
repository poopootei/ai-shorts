"""完成した動画から確認用のコマを並べた画像を作る（hook・各段落の真ん中・最後）。

    python scripts/preview_video.py 20261120-001            # work/{id}/video.mp4
    python scripts/preview_video.py 20261120-001 --crop      # 字幕のあたりを原寸で切り出す（読みやすさの確認）

出力は work/{id}/preview.png（--crop のときは preview_subs.png）。
"""

from __future__ import annotations

import argparse
import os
import json
import subprocess
from pathlib import Path

ROOT = Path(os.environ.get("AI_SHORTS_ROOT") or Path(__file__).resolve().parents[1]).resolve()  # チャンネルごとの作業場所（channels/{name}/）


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("id")
    ap.add_argument("--crop", action="store_true", help="字幕の帯（画面の中ほど）を原寸で切り出す")
    args = ap.parse_args()

    work = ROOT / "work" / args.id
    video = work / "video.mp4"
    timing = json.loads((work / "timing.json").read_text(encoding="utf-8"))
    if args.crop:
        s = timing["sentences"][len(timing["sentences"]) // 2]
        t = (s["start"] + s["end"]) / 2
        out = work / "preview_subs.png"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video),
                        "-vf", "crop=1080:420:0:650", "-frames:v", "1", str(out)], check=True)
    else:
        times = [1.0] + [(p["start"] + p["end"]) / 2 for p in timing["paragraphs"]] + [timing["duration"] - 0.5]
        frames = [round(t * 30) for t in times]
        select = "+".join(f"eq(n\\,{f})" for f in frames)
        out = work / "preview.png"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(video), "-vf",
                        f"select='{select}',scale=270:480,tile={len(frames)}x1", "-frames:v", "1", str(out)],
                       check=True)
        print("コマの時刻:", ", ".join(f"{t:.1f}s" for t in times))
    print(out)


if __name__ == "__main__":
    main()
