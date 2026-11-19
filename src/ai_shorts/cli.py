"""python -m ai_shorts <stage> --id <story_id>"""

from __future__ import annotations

import argparse
import sys
from typing import Callable

from . import qa, render, subs, tts
from .config import Project, load_project
from .errors import AiShortsError
from .story import list_approved

# 実行順。images（ComfyUI）はまだないので、work/{id}/img_*.png は scripts/ で用意する
STAGES: dict[str, Callable[[Project, str], None]] = {
    "tts": tts.run,
    "subs": subs.run,
    "render": render.run,
    "qa": qa.run,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai_shorts", description=__doc__)
    sub = parser.add_subparsers(dest="stage", required=True)
    for name in STAGES:
        p = sub.add_parser(name, help=f"{name} 工程を実行する")
        p.add_argument("--id", required=True, help="物語の id")
    p = sub.add_parser("all", help="実装済みの工程を順に実行する")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--id", help="物語の id")
    g.add_argument("--approved", action="store_true", help="承認済みの物語をすべて処理する")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        project = load_project()
        if args.stage != "all":
            STAGES[args.stage](project, args.id)
            return 0
        ids = list_approved(project) if args.approved else [args.id]
        failed: list[str] = []
        for story_id in ids:
            try:
                for stage in STAGES.values():
                    stage(project, story_id)
            except AiShortsError as e:
                if not args.approved:
                    raise
                print(f"エラー（{story_id}）: {e}", file=sys.stderr)
                failed.append(story_id)
        if failed:
            print(f"失敗: {', '.join(failed)}", file=sys.stderr)
            return 1
        return 0
    except AiShortsError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1
