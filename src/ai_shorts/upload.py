"""投稿（upload）: 動画CHECKに通った upload/{id}.mp4 を YouTube に予約投稿し、posted で記録する。

公開は 1 日 1 本、config.yaml の youtube.publish_time（D-015、policy.md の「投稿」）。
最初の公開日は、これまでの YouTube の公開日（stories/posted/ の history）の翌日。
--dry-run なら予定を表示するだけで、外部へは何も送らない。
"""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import library
from .config import Project
from .errors import AiShortsError, ConfigError

PLATFORM = "youtube"
TITLE_MAX = 100          # YouTube の上限（文字）
DESCRIPTION_MAX = 5000   # YouTube の上限（バイト）
TAGS_MAX = 500           # タグ全体の上限（文字。区切りのカンマも数える）

Uploader = Callable[[Path, dict, Callable[[float], None]], dict]


@dataclass
class Plan:
    id: str
    title: str
    video: Path
    description: str
    tags: list[str] = field(default_factory=list)
    publish_at: dt.datetime | None = None   # タイムゾーン付き


def log(msg: str) -> None:
    print(f"[upload] {msg}")


# --- 設定 ---------------------------------------------------------------

def _tz(project: Project) -> dt.timezone:
    s = str(project.get("youtube.utc_offset"))
    m = re.fullmatch(r"([+-])(\d{2}):(\d{2})", s)
    if not m:
        raise ConfigError(f'youtube.utc_offset は "+09:00" の形で書いてください（いまは {s!r}）。')
    delta = dt.timedelta(hours=int(m[2]), minutes=int(m[3]))
    return dt.timezone(delta if m[1] == "+" else -delta)


def _publish_time(project: Project) -> dt.time:
    s = project.get("youtube.publish_time")
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", s) if isinstance(s, str) else None
    if not m:
        raise ConfigError(f'youtube.publish_time は "18:00" のように引用符で囲んで書いてください（いまは {s!r}）。')
    return dt.time(int(m[1]), int(m[2]))


# --- 公開日 -------------------------------------------------------------

def last_publish_date(project: Project) -> dt.date | None:
    """stories/posted/ の history から、YouTube の公開日のうちいちばん遅いもの。"""
    dates = []
    for path in (project.root / "stories" / "posted").glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        for h in data.get("history", []):
            if h.get("event") == "posted" and h.get("platform") == PLATFORM and h.get("date"):
                try:
                    dates.append(dt.date.fromisoformat(h["date"]))
                except ValueError:
                    pass
    return max(dates) if dates else None


def schedule(project: Project, count: int, now: dt.datetime, start: dt.date | None = None) -> list[dt.datetime]:
    """count 本分の公開日時。1 日 1 本、publish_time に。"""
    tz, at = _tz(project), _publish_time(project)
    earliest = now.astimezone(tz) + dt.timedelta(minutes=int(project.get("youtube.min_lead_minutes")))
    if start:
        first = dt.datetime.combine(start, at, tzinfo=tz)
        if first < earliest:
            raise AiShortsError(f"--start {start} の {at:%H:%M} はもう過ぎているか、近すぎます。")
    else:
        last = last_publish_date(project)
        day = max(last + dt.timedelta(days=1), earliest.date()) if last else earliest.date()
        first = dt.datetime.combine(day, at, tzinfo=tz)
        while first < earliest:
            first += dt.timedelta(days=1)
    return [first + dt.timedelta(days=i) for i in range(count)]


# --- 投稿の中身 ---------------------------------------------------------

def pending_ids(project: Project) -> list[str]:
    return sorted(p.stem for p in (project.root / "upload").glob("*.mp4"))


def _check_text(label: str, text: str) -> None:
    if "<" in text or ">" in text:
        raise AiShortsError(f"{label}に < や > があります（YouTube では使えません）。")


def make_plan(project: Project, story_id: str) -> Plan:
    state, path = library.find_story(project, story_id)
    if state != "approved":
        raise AiShortsError(f"{story_id} は stories/{state}/ にあります。投稿できるのは動画CHECKに通った物語だけです。")
    video = project.root / "upload" / f"{story_id}.mp4"
    text = project.root / "upload" / f"{story_id}.txt"
    if not video.exists():
        hint = "（ready/ にあります。先に approve-video で動画CHECKを通してください）" \
            if (project.root / "ready" / f"{story_id}.mp4").exists() else ""
        raise AiShortsError(f"upload/{story_id}.mp4 がありません{hint}。")
    if not text.exists():
        raise AiShortsError(f"upload/{story_id}.txt（説明文）がありません。qa をやり直してください。")
    data = json.loads(path.read_text(encoding="utf-8"))
    title = str(data.get("title", "")).strip()
    description = text.read_text(encoding="utf-8").strip()
    tags = [str(t).strip() for t in data.get("tags", []) if str(t).strip()]
    if not title:
        raise AiShortsError(f"{story_id} の物語にタイトルがありません。")
    if len(title) > TITLE_MAX:
        raise AiShortsError(f"{story_id} のタイトルが {len(title)} 字です（上限 {TITLE_MAX} 字）。")
    if len(description.encode("utf-8")) > DESCRIPTION_MAX:
        raise AiShortsError(f"upload/{story_id}.txt が長すぎます（上限 {DESCRIPTION_MAX} バイト）。")
    if len(",".join(tags)) > TAGS_MAX:
        raise AiShortsError(f"{story_id} のタグが長すぎます（合わせて {TAGS_MAX} 字まで）。")
    _check_text(f"{story_id} のタイトル", title)
    _check_text(f"upload/{story_id}.txt", description)
    for t in tags:
        _check_text(f"{story_id} のタグ", t)
    return Plan(story_id, title, video, description, tags)


def video_body(project: Project, plan: Plan) -> dict:
    """videos.insert に送る中身。非公開で上げて、publishAt に公開される（予約投稿）。"""
    lang = str(project.get("youtube.language"))
    return {
        "snippet": {
            "title": plan.title,
            "description": plan.description,
            "tags": plan.tags,
            "categoryId": str(project.get("youtube.category_id")),
            "defaultLanguage": lang,
            "defaultAudioLanguage": lang,
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": plan.publish_at.isoformat(),
            "selfDeclaredMadeForKids": bool(project.get("youtube.made_for_kids")),
            "containsSyntheticMedia": bool(project.get("youtube.contains_synthetic_media")),
        },
    }


def plans_for(project: Project, ids: list[str], now: dt.datetime, start: dt.date | None = None) -> list[Plan]:
    if not ids:
        raise AiShortsError("投稿待ち（upload/）の動画がありません。")
    if len(set(ids)) != len(ids):
        raise AiShortsError("同じ id が 2 回あります。")
    plans = [make_plan(project, i) for i in ids]
    for plan, when in zip(plans, schedule(project, len(plans), now, start)):
        plan.publish_at = when
    return plans


# --- 実行 ---------------------------------------------------------------

def _progress(story_id: str) -> Callable[[float], None]:
    def show(p: float) -> None:
        log(f"{story_id}: {p * 100:.0f}%")
    return show


def run(project: Project, ids: list[str], *, start: dt.date | None = None, dry_run: bool = False,
        now: dt.datetime | None = None, uploader: Uploader | None = None) -> list[Plan]:
    now = now or dt.datetime.now(dt.timezone.utc)
    plans = plans_for(project, ids, now, start)
    for p in plans:
        log(f"{p.id}「{p.title}」→ {p.publish_at:%Y-%m-%d %H:%M} 公開")
    if dry_run:
        log("--dry-run なので投稿していません。")
        return plans
    if uploader is None:
        from . import youtube
        uploader = youtube.make_uploader(project)
    for p in plans:
        log(f"{p.id}: アップロード中")
        response = uploader(p.video, video_body(project, p), _progress(p.id))
        video_id = response.get("id")
        if not video_id:
            raise AiShortsError(f"{p.id}: YouTube の応答に動画の id がありません: {response}")
        url = f"https://www.youtube.com/shorts/{video_id}"
        log(f"{p.id}: 投稿しました {url}")
        status = response.get("status", {})
        if not status.get("publishAt"):
            log(f"{p.id}: 注意 予約公開の日時が付いていません（privacyStatus={status.get('privacyStatus')}）。"
                "YouTube Studio で公開設定を確かめてください。")
        library.record_post(project, p.id, PLATFORM, url, date=p.publish_at.date().isoformat())
    return plans
