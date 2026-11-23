import datetime as dt
import json

import pytest

from ai_shorts import upload
from ai_shorts.cli import main
from ai_shorts.config import Project
from ai_shorts.errors import AiShortsError, ConfigError

JST = dt.timezone(dt.timedelta(hours=9))
# 2026-11-20 10:00 JST（公開時刻 18:00 より前）
MORNING = dt.datetime(2026, 11, 20, 10, 0, tzinfo=JST)
EVENING = dt.datetime(2026, 11, 20, 17, 30, tzinfo=JST)

YT = {
    "client_secret": "secrets/c.json", "token": "secrets/t.json",
    "publish_time": "18:00", "utc_offset": "+09:00", "min_lead_minutes": 60,
    "category_id": 24, "language": "ja", "made_for_kids": False, "contains_synthetic_media": False,
}


@pytest.fixture
def project(tmp_path):
    return Project(root=tmp_path, config={"youtube": dict(YT)})


def put_story(project, state, sid, **extra):
    d = project.root / "stories" / state
    d.mkdir(parents=True, exist_ok=True)
    data = {"id": sid, "title": f"題{sid[-1]}", "hook": "h", "body": "b", "tags": ["ショートショート", "朗読"],
            "approved": state != "draft", **extra}
    (d / f"{sid}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return d / f"{sid}.json"


def put_video(project, sid, folder="upload", text="題\n\n説明\n"):
    d = project.root / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{sid}.mp4").write_bytes(b"mp4")
    (d / f"{sid}.txt").write_text(text, encoding="utf-8")


def ready_to_post(project, *sids):
    for sid in sids:
        put_story(project, "approved", sid)
        put_video(project, sid)


def posted_on(project, sid, date, platform="youtube"):
    put_story(project, "posted", sid, history=[{"date": date, "event": "posted", "platform": platform}])


class FakeUploader:
    def __init__(self):
        self.calls = []

    def __call__(self, video, body, on_progress):
        self.calls.append((video, body))
        on_progress(1.0)
        n = len(self.calls)
        return {"id": f"vid{n}", "status": {"privacyStatus": "private", "publishAt": body["status"]["publishAt"]}}


# --- 公開日 -------------------------------------------------------------

def test_schedule_today_when_slot_is_ahead(project):
    slots = upload.schedule(project, 2, MORNING)
    assert [s.isoformat() for s in slots] == ["2026-11-20T18:00:00+09:00", "2026-11-21T18:00:00+09:00"]


def test_schedule_tomorrow_when_slot_is_too_close(project):
    assert upload.schedule(project, 1, EVENING)[0].date() == dt.date(2026, 11, 21)


def test_schedule_continues_after_last_publish_date(project):
    posted_on(project, "20261119-001", "2026-11-24")
    posted_on(project, "20261119-002", "2026-11-23")
    posted_on(project, "20261119-003", "2026-11-30", platform="instagram")
    assert upload.schedule(project, 1, MORNING)[0].date() == dt.date(2026, 11, 25)


def test_schedule_ignores_old_publish_dates(project):
    posted_on(project, "20261101-001", "2026-11-01")
    assert upload.schedule(project, 1, MORNING)[0].date() == dt.date(2026, 11, 20)


def test_schedule_with_start(project):
    assert upload.schedule(project, 1, MORNING, start=dt.date(2026, 12, 1))[0].date() == dt.date(2026, 12, 1)
    with pytest.raises(AiShortsError, match="過ぎて"):
        upload.schedule(project, 1, EVENING, start=dt.date(2026, 11, 20))


def test_publish_time_must_be_quoted(project):
    project.config["youtube"]["publish_time"] = 1080  # YAML で 18:00 を引用符なしで書くと 1080 になる
    with pytest.raises(ConfigError, match="引用符"):
        upload.schedule(project, 1, MORNING)


def test_utc_offset_format(project):
    project.config["youtube"]["utc_offset"] = "JST"
    with pytest.raises(ConfigError):
        upload.schedule(project, 1, MORNING)


# --- 投稿の中身 ---------------------------------------------------------

def test_plan_and_body(project):
    ready_to_post(project, "20261120-001")
    plan = upload.plans_for(project, ["20261120-001"], MORNING)[0]
    body = upload.video_body(project, plan)
    assert body["snippet"] == {
        "title": "題1", "description": "題\n\n説明", "tags": ["ショートショート", "朗読"],
        "categoryId": "24", "defaultLanguage": "ja", "defaultAudioLanguage": "ja",
    }
    assert body["status"] == {
        "privacyStatus": "private", "publishAt": "2026-11-20T18:00:00+09:00",
        "selfDeclaredMadeForKids": False, "containsSyntheticMedia": False,
    }


def test_plan_requires_video_check(project):
    put_story(project, "approved", "20261120-001")
    put_video(project, "20261120-001", folder="ready")
    with pytest.raises(AiShortsError, match="approve-video"):
        upload.make_plan(project, "20261120-001")


def test_plan_refuses_posted_story(project):
    posted_on(project, "20261120-001", "2026-11-19")
    with pytest.raises(AiShortsError, match="stories/posted"):
        upload.make_plan(project, "20261120-001")


def test_plan_rejects_angle_brackets(project):
    put_story(project, "approved", "20261120-001")
    put_video(project, "20261120-001", text="<b>説明</b>")
    with pytest.raises(AiShortsError, match="<"):
        upload.make_plan(project, "20261120-001")


def test_plan_rejects_long_title(project):
    put_story(project, "approved", "20261120-001", title="あ" * 101)
    put_video(project, "20261120-001")
    with pytest.raises(AiShortsError, match="101 字"):
        upload.make_plan(project, "20261120-001")


def test_duplicate_ids(project):
    ready_to_post(project, "20261120-001")
    with pytest.raises(AiShortsError, match="2 回"):
        upload.plans_for(project, ["20261120-001", "20261120-001"], MORNING)


# --- 実行 ---------------------------------------------------------------

def test_dry_run_does_not_upload(project):
    ready_to_post(project, "20261120-001")
    fake = FakeUploader()
    upload.run(project, ["20261120-001"], dry_run=True, now=MORNING, uploader=fake)
    assert fake.calls == []
    assert (project.root / "upload" / "20261120-001.mp4").exists()


def test_run_uploads_in_order_and_records(project):
    posted_on(project, "20261119-001", "2026-11-21")
    ready_to_post(project, "20261120-001", "20261120-002")
    fake = FakeUploader()
    upload.run(project, ["20261120-002", "20261120-001"], now=MORNING, uploader=fake)

    assert [c[0].name for c in fake.calls] == ["20261120-002.mp4", "20261120-001.mp4"]
    assert [c[1]["status"]["publishAt"] for c in fake.calls] == [
        "2026-11-22T18:00:00+09:00", "2026-11-23T18:00:00+09:00"]
    for sid, vid, date in (("20261120-002", "vid1", "2026-11-22"), ("20261120-001", "vid2", "2026-11-23")):
        data = json.loads((project.root / "stories" / "posted" / f"{sid}.json").read_text(encoding="utf-8"))
        assert data["history"][-1] == {"date": date, "event": "posted", "platform": "youtube",
                                       "url": f"https://www.youtube.com/shorts/{vid}"}
        assert (project.root / "posted" / f"{sid}.mp4").exists()
        assert not (project.root / "upload" / f"{sid}.mp4").exists()
    # 次に上げるときは、この続きの日に入る
    assert upload.schedule(project, 1, MORNING)[0].date() == dt.date(2026, 11, 24)


def test_run_stops_without_video_id(project):
    ready_to_post(project, "20261120-001")
    with pytest.raises(AiShortsError, match="id"):
        upload.run(project, ["20261120-001"], now=MORNING, uploader=lambda v, b, p: {})
    assert (project.root / "upload" / "20261120-001.mp4").exists()


def test_cli_requires_ids_or_all(project, monkeypatch, capsys):
    monkeypatch.setattr("ai_shorts.cli.load_project", lambda **kw: project)
    assert main(["upload"]) == 1
    assert "--all" in capsys.readouterr().err


def test_cli_all_dry_run(project, monkeypatch, capsys):
    monkeypatch.setattr("ai_shorts.cli.load_project", lambda **kw: project)
    ready_to_post(project, "20261120-002", "20261120-001")
    assert main(["upload", "--all", "--dry-run", "--start", "2030-01-01"]) == 0
    out = capsys.readouterr().out
    assert out.index("20261120-001") < out.index("20261120-002")
    assert "2030-01-01 18:00" in out and "2030-01-02 18:00" in out
