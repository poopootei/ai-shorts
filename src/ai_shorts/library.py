"""物語と動画の状態の管理（CHECK・ボツ・投稿の記録）。

状態はフォルダで表し、経緯は物語 JSON の "history" に残す（git で管理される）。

    stories/draft/      物語CHECK待ち
    stories/approved/   物語CHECK合格。動画は work/ → ready/（動画CHECK待ち）→ upload/（投稿待ち）
    stories/posted/     投稿済み。動画は posted/
    stories/rejected/   ボツ（物語でも動画でも）。ボツ動画は rejected/

ボツにするときは理由（reason）と改善案（idea）を必ず残す。次に物語を書くときと
動画を作るときに `python -m ai_shorts ideas` で読み返す。
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from .config import Project
from .errors import AiShortsError

STORY_STATES = ("draft", "approved", "posted", "rejected")


@dataclass
class Row:
    id: str
    title: str
    state: str   # 画面に出す状態
    detail: str  # 次にやること・投稿先など


@dataclass
class Rejection:
    id: str
    title: str
    stage: str   # "物語" / "動画"
    date: str
    reason: str
    idea: str
    file: str = ""


def _today(today: dt.date | None) -> str:
    return (today or dt.date.today()).isoformat()


def find_story(project: Project, story_id: str) -> tuple[str, Path]:
    found = [(s, project.root / "stories" / s / f"{story_id}.json") for s in STORY_STATES]
    found = [(s, p) for s, p in found if p.exists()]
    if not found:
        raise AiShortsError(f"物語 {story_id} が stories/ のどこにもありません。")
    if len(found) > 1:
        where = ", ".join(f"stories/{s}/" for s, _ in found)
        raise AiShortsError(f"物語 {story_id} が複数の場所にあります（{where}）。1つにしてください。")
    return found[0]


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise AiShortsError(f"{path} の JSON が読めません: {e}") from e


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def add_history(data: dict, event: str, date: str, **fields: str) -> None:
    entry = {"date": date, "event": event}
    entry.update({k: v for k, v in fields.items() if v})
    data.setdefault("history", []).append(entry)


def _move_story(project: Project, src: Path, state: str, data: dict) -> Path:
    dst = project.root / "stories" / state / src.name
    if dst != src and dst.exists():
        raise AiShortsError(f"{dst} はもうあります。")
    _write(dst, data)
    if dst != src:
        src.unlink()
    return dst


def _require_reason(reason: str, idea: str) -> None:
    if not reason.strip() or not idea.strip():
        raise AiShortsError("ボツにするときは、理由（--reason）と改善案（--idea）を両方書いてください。")


def _video_files(folder: Path, story_id: str) -> list[Path]:
    return [p for p in (folder / f"{story_id}.mp4", folder / f"{story_id}.txt") if p.exists()]


def _move_files(files: list[Path], folder: Path, stem: str) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    moved = []
    for f in files:
        dst = folder / f"{stem}{f.suffix}"
        dst.unlink(missing_ok=True)
        shutil.move(str(f), str(dst))
        moved.append(dst)
    return moved


def _rel(project: Project, p: Path) -> str:
    return p.relative_to(project.root).as_posix()


# --- 物語 ---------------------------------------------------------------

def reject_story(project: Project, story_id: str, reason: str, idea: str,
                 today: dt.date | None = None) -> Path:
    """物語CHECKでボツ。draft / approved（動画がまだないもの）→ stories/rejected/"""
    _require_reason(reason, idea)
    state, path = find_story(project, story_id)
    if state not in ("draft", "approved"):
        raise AiShortsError(f"{story_id} は stories/{state}/ にあります。ボツにできるのは draft と approved だけです。")
    for folder in ("ready", "upload"):
        if _video_files(project.root / folder, story_id):
            raise AiShortsError(
                f"{story_id} の動画が {folder}/ にあります。動画ごとボツにするなら reject-video を使ってください。")
    data = _read(path)
    data["approved"] = False
    add_history(data, "story_rejected", _today(today), reason=reason, idea=idea, **{"from": state})
    return _move_story(project, path, "rejected", data)


def revive_story(project: Project, story_id: str, note: str = "",
                 today: dt.date | None = None) -> Path:
    """ボツにした物語を直すために stories/draft/ へ戻す。もう一度物語CHECKを通す。"""
    state, path = find_story(project, story_id)
    if state != "rejected":
        raise AiShortsError(f"{story_id} はボツではありません（stories/{state}/）。")
    data = _read(path)
    data["approved"] = False
    add_history(data, "story_revived", _today(today), note=note)
    return _move_story(project, path, "draft", data)


# --- 動画 ---------------------------------------------------------------

def approve_video(project: Project, story_id: str, note: str = "",
                  today: dt.date | None = None) -> list[Path]:
    """動画CHECK合格。ready/{id}.mp4, .txt → upload/（投稿待ち）"""
    state, path = find_story(project, story_id)
    if state != "approved":
        raise AiShortsError(f"{story_id} は stories/{state}/ にあります（動画CHECKは approved の物語だけ）。")
    files = _video_files(project.root / "ready", story_id)
    if not any(f.suffix == ".mp4" for f in files):
        raise AiShortsError(f"ready/{story_id}.mp4 がありません。先に動画を作って QA に通してください。")
    moved = _move_files(files, project.root / "upload", story_id)
    data = _read(path)
    add_history(data, "video_approved", _today(today), note=note)
    _write(path, data)
    return moved


def reject_video(project: Project, story_id: str, reason: str, idea: str, *, remake: bool,
                 today: dt.date | None = None) -> list[Path]:
    """動画CHECKでボツ。ready/（または upload/）の動画 → rejected/{id}-{n}.mp4

    remake=True なら物語は approved に残して作り直す。False なら物語ごと stories/rejected/ へ。
    """
    _require_reason(reason, idea)
    state, path = find_story(project, story_id)
    if state != "approved":
        raise AiShortsError(f"{story_id} は stories/{state}/ にあります（動画をボツにできるのは approved の物語だけ）。")
    files = _video_files(project.root / "ready", story_id) or _video_files(project.root / "upload", story_id)
    if not any(f.suffix == ".mp4" for f in files):
        raise AiShortsError(f"{story_id} の動画が ready/ にも upload/ にもありません。")
    rejected = project.root / "rejected"
    n = 1
    while (rejected / f"{story_id}-{n}.mp4").exists():
        n += 1
    moved = _move_files(files, rejected, f"{story_id}-{n}")
    video = next(p for p in moved if p.suffix == ".mp4")
    data = _read(path)
    add_history(data, "video_rejected", _today(today), reason=reason, idea=idea,
                file=_rel(project, video), next="作り直す" if remake else "ボツ")
    if remake:
        _write(path, data)
    else:
        data["approved"] = False
        _move_story(project, path, "rejected", data)
    return moved


def record_post(project: Project, story_id: str, platform: str, url: str = "",
                date: str = "", today: dt.date | None = None) -> list[Path]:
    """投稿したことを記録する。upload/ → posted/、物語 → stories/posted/。

    もう投稿済みの物語なら、別の投稿先として記録を足すだけ（動画は posted/ のまま）。
    """
    if not platform.strip():
        raise AiShortsError("投稿先（--platform）を書いてください。")
    state, path = find_story(project, story_id)
    data = _read(path)
    when = date or _today(today)
    if state == "posted":
        add_history(data, "posted", when, platform=platform, url=url)
        _write(path, data)
        return []
    if state != "approved":
        raise AiShortsError(f"{story_id} は stories/{state}/ にあります。投稿できるのは動画CHECKに通った物語だけです。")
    files = _video_files(project.root / "upload", story_id)
    if not any(f.suffix == ".mp4" for f in files):
        hint = "（ready/ にあります。先に approve-video で動画CHECKを通してください）" \
            if _video_files(project.root / "ready", story_id) else ""
        raise AiShortsError(f"upload/{story_id}.mp4 がありません{hint}。")
    moved = _move_files(files, project.root / "posted", story_id)
    add_history(data, "posted", when, platform=platform, url=url)
    _move_story(project, path, "posted", data)
    return moved


# --- 一覧 ---------------------------------------------------------------

def _events(data: dict, event: str) -> list[dict]:
    return [h for h in data.get("history", []) if h.get("event") == event]


def _video_state(project: Project, story_id: str) -> tuple[str, str]:
    root = project.root
    if (root / "ready" / f"{story_id}.mp4").exists():
        return "動画CHECK待ち", f"ready/{story_id}.mp4 を見て OK なら approve-video、だめなら reject-video"
    if (root / "upload" / f"{story_id}.mp4").exists():
        return "投稿待ち", f"upload/{story_id}.mp4 を投稿したら posted で記録"
    qa = root / "work" / story_id / "qa.json"
    if qa.exists():
        try:
            if not json.loads(qa.read_text(encoding="utf-8")).get("passed"):
                return "QA NG", f"work/{story_id}/qa.json を見て直す"
        except json.JSONDecodeError:
            pass
    return "動画づくり待ち", "背景を選んで all --id で作る"


def status(project: Project) -> list[Row]:
    rows: list[Row] = []
    for state in STORY_STATES:
        for path in sorted((project.root / "stories" / state).glob("*.json")):
            data = _read(path)
            sid, title = path.stem, data.get("title", "")
            if state == "draft":
                rows.append(Row(sid, title, "物語CHECK待ち", "全文を読んで承認かボツか決める"))
            elif state == "approved":
                rows.append(Row(sid, title, *_video_state(project, sid)))
            elif state == "posted":
                posts = _events(data, "posted")
                where = ", ".join(f"{p.get('platform')} {p.get('date')}" for p in posts)
                rows.append(Row(sid, title, "投稿済み", where))
            else:
                last = (data.get("history") or [{}])[-1]
                stage = "動画" if last.get("event") == "video_rejected" else "物語"
                rows.append(Row(sid, title, f"ボツ（{stage}）", last.get("reason", "")))
    return rows


def rejections(project: Project) -> list[Rejection]:
    """全物語の history から、ボツの理由と改善案を日付順に集める（作り直したものも含む）。"""
    out: list[Rejection] = []
    for state in STORY_STATES:
        for path in sorted((project.root / "stories" / state).glob("*.json")):
            data = _read(path)
            for h in data.get("history", []):
                if h.get("event") in ("story_rejected", "video_rejected"):
                    out.append(Rejection(
                        id=path.stem, title=data.get("title", ""),
                        stage="物語" if h["event"] == "story_rejected" else "動画",
                        date=h.get("date", ""), reason=h.get("reason", ""),
                        idea=h.get("idea", ""), file=h.get("file", ""),
                    ))
    return sorted(out, key=lambda r: (r.date, r.id))
