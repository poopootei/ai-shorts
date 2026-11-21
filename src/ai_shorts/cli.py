"""python -m ai_shorts <stage> --id <story_id>

動画を作る工程（tts / subs / render / qa / all）と、状態の管理
（status / ideas / approve-video / reject-video / posted / reject-story / revive-story）、
YouTube への予約投稿（upload / youtube-login）、タブレットへの受け渡し（share）。
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from typing import Callable

from . import library, qa, render, subs, tts, upload
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
    parser = argparse.ArgumentParser(prog="ai_shorts", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="stage", required=True)
    for name in STAGES:
        p = sub.add_parser(name, help=f"{name} 工程を実行する")
        p.add_argument("--id", required=True, help="物語の id")
    p = sub.add_parser("all", help="実装済みの工程を順に実行する")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--id", help="物語の id")
    g.add_argument("--approved", action="store_true",
                   help="承認済みでまだ動画がない物語をまとめて処理する（ready/ や upload/ にあるものは飛ばす）")

    sub.add_parser("status", help="物語と動画の状態の一覧")
    sub.add_parser("ideas", help="これまでのボツの理由と改善案")

    p = sub.add_parser("approve-video", help="動画CHECK合格：ready/ → upload/（投稿待ち）")
    p.add_argument("ids", nargs="+")
    p.add_argument("--note", default="", help="ユーザーのコメント")

    p = sub.add_parser("reject-video", help="動画CHECKでボツ：ready/ → rejected/")
    p.add_argument("id")
    p.add_argument("--reason", required=True, help="ボツの理由")
    p.add_argument("--idea", required=True, help="改善案（次にどうするか）")
    m = p.add_mutually_exclusive_group(required=True)
    m.add_argument("--remake", action="store_true", help="物語は残して動画を作り直す")
    m.add_argument("--drop", action="store_true", help="物語ごとボツにする")

    p = sub.add_parser("posted", help="投稿したことを記録する：upload/ → posted/")
    p.add_argument("id")
    p.add_argument("--platform", default="youtube", help="投稿先（youtube / instagram など）")
    p.add_argument("--url", default="", help="動画の URL")
    p.add_argument("--date", default="", help="投稿日（予約投稿なら公開日）YYYY-MM-DD。省略すると今日")

    p = sub.add_parser("upload", help="投稿待ち（upload/）を YouTube に予約投稿し、posted で記録する")
    p.add_argument("ids", nargs="*", help="物語の id（公開はこの順に 1 日 1 本）")
    p.add_argument("--all", action="store_true", help="upload/ にあるものをすべて（id の順）")
    p.add_argument("--start", default="", help="最初の公開日 YYYY-MM-DD。省略すると、これまでの公開日の翌日")
    p.add_argument("--dry-run", action="store_true", help="公開の予定を表示するだけで、投稿しない")

    sub.add_parser("youtube-login", help="YouTube にログインする（初回・ログインが切れたとき）")

    p = sub.add_parser("share", help="投稿待ち（upload/）を MiniPC に送り、タブレットで保存・コピーできるようにする")
    p.add_argument("--install", action="store_true", help="MiniPC にサーバーを置いて起動し直す（初回・server.py を変えたとき）")

    p = sub.add_parser("reject-story", help="物語CHECKでボツ：stories/draft → stories/rejected")
    p.add_argument("id")
    p.add_argument("--reason", required=True, help="ボツの理由")
    p.add_argument("--idea", required=True, help="改善案（次にどう書くか）")

    p = sub.add_parser("revive-story", help="ボツの物語を直すために stories/draft/ へ戻す")
    p.add_argument("id")
    p.add_argument("--note", default="", help="戻す理由")
    return parser


def run_all(project: Project, args: argparse.Namespace) -> int:
    if not args.approved:
        for stage in STAGES.values():
            stage(project, args.id)
        return 0
    ids = []
    for story_id in list_approved(project):
        made = [d for d in ("ready", "upload") if (project.root / d / f"{story_id}.mp4").exists()]
        if made:
            print(f"スキップ（{story_id}）: {made[0]}/ に動画があります。作り直すなら --id で。")
        else:
            ids.append(story_id)
    failed: list[str] = []
    for story_id in ids:
        try:
            for stage in STAGES.values():
                stage(project, story_id)
        except AiShortsError as e:
            print(f"エラー（{story_id}）: {e}", file=sys.stderr)
            failed.append(story_id)
    if failed:
        print(f"失敗: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


def print_status(project: Project) -> None:
    rows = library.status(project)
    if not rows:
        print("物語がありません。")
        return
    order = ["物語CHECK待ち", "動画づくり待ち", "QA NG", "動画CHECK待ち", "投稿待ち", "投稿済み"]
    rows.sort(key=lambda r: (order.index(r.state) if r.state in order else len(order), r.id))
    current = None
    for r in rows:
        if r.state != current:
            current = r.state
            print(f"\n■ {current}")
        print(f"  {r.id}  {r.title}" + (f"  — {r.detail}" if r.detail else ""))


def print_ideas(project: Project) -> None:
    items = library.rejections(project)
    if not items:
        print("ボツの記録はまだありません。")
        return
    for stage in ("物語", "動画"):
        group = [r for r in items if r.stage == stage]
        if not group:
            continue
        print(f"\n■ {stage}のボツ（{len(group)} 件）")
        for r in group:
            print(f"- {r.date} {r.id}「{r.title}」" + (f"  {r.file}" if r.file else ""))
            print(f"    理由: {r.reason}")
            print(f"    改善案: {r.idea}")


def run_upload(project: Project, args: argparse.Namespace) -> None:
    if args.all == bool(args.ids):
        raise AiShortsError("id を並べるか、--all を付けてください（どちらか一方）。")
    ids = upload.pending_ids(project) if args.all else args.ids
    try:
        start = dt.date.fromisoformat(args.start) if args.start else None
    except ValueError as e:
        raise AiShortsError(f"--start は YYYY-MM-DD で書いてください（{args.start}）。") from e
    upload.run(project, ids, start=start, dry_run=args.dry_run)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        project = load_project()
        if args.stage in STAGES:
            STAGES[args.stage](project, args.id)
        elif args.stage == "all":
            return run_all(project, args)
        elif args.stage == "status":
            print_status(project)
        elif args.stage == "ideas":
            print_ideas(project)
        elif args.stage == "approve-video":
            for story_id in args.ids:
                library.approve_video(project, story_id, args.note)
                print(f"動画CHECK合格 → upload/{story_id}.mp4（投稿待ち）")
        elif args.stage == "reject-video":
            moved = library.reject_video(project, args.id, args.reason, args.idea, remake=args.remake)
            video = next(p for p in moved if p.suffix == ".mp4")
            print(f"ボツ動画 → {video.relative_to(project.root).as_posix()}")
            print("物語は stories/approved/ に残しました（作り直す）。" if args.remake
                  else f"物語も stories/rejected/{args.id}.json に移しました。")
        elif args.stage == "posted":
            moved = library.record_post(project, args.id, args.platform, args.url, args.date)
            print(f"投稿を記録（{args.platform}）" +
                  (f" → posted/{args.id}.mp4" if moved else "（投稿済みの物語に追記）"))
        elif args.stage == "upload":
            run_upload(project, args)
        elif args.stage == "youtube-login":
            from . import youtube
            youtube.login(project, force=True)
            print("YouTube にログインしました。")
        elif args.stage == "share":
            from . import share
            if args.install:
                share.install(project)
            share.sync(project)
        elif args.stage == "reject-story":
            path = library.reject_story(project, args.id, args.reason, args.idea)
            print(f"ボツ → {path.relative_to(project.root).as_posix()}")
        elif args.stage == "revive-story":
            path = library.revive_story(project, args.id, args.note)
            print(f"下書きに戻しました → {path.relative_to(project.root).as_posix()}（もう一度物語CHECKを通す）")
        return 0
    except AiShortsError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1
