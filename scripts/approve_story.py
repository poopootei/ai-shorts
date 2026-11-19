"""人が承認した物語を stories/draft/ から stories/approved/ に移す。

    python scripts/approve_story.py 20261120-001 --note "オチを1文短くした" [--voice ofutonp]

**ユーザーが承認したときだけ実行する**（CLAUDE.md の決まり 6。Claude が自分で承認しない）。
approved: true にし、notes の先頭に「YYYY-MM-DD ユーザーが承認」と、直した点を書く。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--note", default="本文の修正なし", help="人が直した点（notes に残る）")
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
        d["notes"] = f"{dt.date.today().isoformat()} ユーザーが承認（{args.note}）。" + (d.get("notes") or "")
        dst.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # 検査に通らなければ元に戻す
        rc = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_story.py"), str(dst)]).returncode
        if rc != 0:
            dst.unlink()
            sys.exit(f"{sid} は検査で NG があったので承認していません（draft のまま）。")
        src.unlink()
        print(f"承認: {dst.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
