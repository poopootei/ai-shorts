"""検査に通った物語を stories/draft/ から stories/approved/ に移す。

    python scripts/approve_story.py 20261120-001 [--note "オチを1文短くした"] [--voice ofutonp]

物語CHECK はしない（docs/decisions.md D-018）。Claude が書いて検査に通したら実行し、人は動画CHECK で判断する。
approved: true にし、notes の先頭に「YYYY-MM-DD 承認」と、直した点を書く（history にも残す）。
ボツにするときは `python -m ai_shorts reject-story <id> --reason ... --idea ...`。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ai_shorts.config import add_channel_arg, script_root  # noqa: E402

ROOT = script_root()  # チャンネルのフォルダ（channels/{name}/）。--channel で選ぶ


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_channel_arg(ap)
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--note", default="検査に合格。物語CHECK なし（D-018）", help="直した点など（notes に残る）")
    ap.add_argument("--voice", help="声を決めたときに上書きする（config.yaml の voices のキー）")
    args = ap.parse_args()

    for sid in args.ids:
        src = ROOT / "stories" / "draft" / f"{sid}.json"
        dst = ROOT / "stories" / "approved" / f"{sid}.json"
        if dst.exists():
            sys.exit(f"{dst} はもうあります。")
        if not src.exists():
            sys.exit(f"{src} がありません。")
        d = json.loads(src.read_text(encoding="utf-8"))
        if args.voice:
            d["voice"] = args.voice
        d["approved"] = True
        d["notes"] = f"{dt.date.today().isoformat()} 承認（{args.note}）。" + (d.get("notes") or "")
        # 経緯は history に残す（python -m ai_shorts status / ideas が読む）
        d.setdefault("history", []).append(
            {"date": dt.date.today().isoformat(), "event": "story_approved", "note": args.note})
        dst.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # 検査に通らなければ元に戻す
        rc = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "check_story.py"), str(dst)]).returncode
        if rc != 0:
            dst.unlink()
            sys.exit(f"{sid} は検査で NG があったので承認していません（draft のまま）。")
        src.unlink()
        print(f"承認: {dst.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
