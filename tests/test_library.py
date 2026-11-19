import datetime as dt
import json

import pytest

from ai_shorts import library
from ai_shorts.cli import main
from ai_shorts.config import Project
from ai_shorts.errors import AiShortsError

DAY = dt.date(2026, 11, 20)


@pytest.fixture
def project(tmp_path):
    return Project(root=tmp_path, config={})


def put_story(project, state, sid="20261120-001", **extra):
    d = project.root / "stories" / state
    d.mkdir(parents=True, exist_ok=True)
    data = {"id": sid, "title": "題", "hook": "h", "body": "b", "approved": state == "approved", **extra}
    (d / f"{sid}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return d / f"{sid}.json"


def put_video(project, folder, sid="20261120-001"):
    d = project.root / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{sid}.mp4").write_bytes(b"mp4")
    (d / f"{sid}.txt").write_text("説明", encoding="utf-8")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_reject_story_moves_and_records(project):
    put_story(project, "draft")
    path = library.reject_story(project, "20261120-001", "オチが読める", "ひねりを2段に", today=DAY)
    assert path == project.root / "stories" / "rejected" / "20261120-001.json"
    assert not (project.root / "stories" / "draft" / "20261120-001.json").exists()
    h = read(path)["history"][-1]
    assert h == {"date": "2026-11-20", "event": "story_rejected", "reason": "オチが読める",
                 "idea": "ひねりを2段に", "from": "draft"}


def test_reject_requires_reason_and_idea(project):
    put_story(project, "draft")
    with pytest.raises(AiShortsError):
        library.reject_story(project, "20261120-001", "理由だけ", " ")


def test_reject_story_refuses_when_video_exists(project):
    put_story(project, "approved")
    put_video(project, "ready")
    with pytest.raises(AiShortsError, match="reject-video"):
        library.reject_story(project, "20261120-001", "r", "i")


def test_revive_story_goes_back_to_draft(project):
    put_story(project, "rejected", approved=True)
    path = library.revive_story(project, "20261120-001", "改善案で書き直す", today=DAY)
    assert path.parent.name == "draft"
    data = read(path)
    assert data["approved"] is False
    assert data["history"][-1]["event"] == "story_revived"


def test_full_lifecycle_to_posted(project):
    put_story(project, "approved")
    put_video(project, "ready")
    library.approve_video(project, "20261120-001", "OK", today=DAY)
    assert (project.root / "upload" / "20261120-001.mp4").exists()
    assert (project.root / "upload" / "20261120-001.txt").exists()
    assert not (project.root / "ready" / "20261120-001.mp4").exists()

    library.record_post(project, "20261120-001", "youtube", "https://youtu.be/x", today=DAY)
    assert (project.root / "posted" / "20261120-001.mp4").exists()
    story = project.root / "stories" / "posted" / "20261120-001.json"
    events = [h["event"] for h in read(story)["history"]]
    assert events == ["video_approved", "posted"]

    # 別の投稿先は追記だけ
    library.record_post(project, "20261120-001", "instagram", date="2026-11-21")
    posts = [h for h in read(story)["history"] if h["event"] == "posted"]
    assert [(p["platform"], p["date"]) for p in posts] == [("youtube", "2026-11-20"), ("instagram", "2026-11-21")]


def test_post_requires_video_check(project):
    put_story(project, "approved")
    put_video(project, "ready")
    with pytest.raises(AiShortsError, match="approve-video"):
        library.record_post(project, "20261120-001", "youtube")


def test_reject_video_remake_keeps_story_and_numbers_takes(project):
    put_story(project, "approved")
    put_video(project, "ready")
    library.reject_video(project, "20261120-001", "背景が暗い", "明るい写真に", remake=True, today=DAY)
    put_video(project, "ready")
    library.reject_video(project, "20261120-001", "字幕が小さい", "font_size を上げる", remake=True, today=DAY)
    rej = project.root / "rejected"
    assert (rej / "20261120-001-1.mp4").exists() and (rej / "20261120-001-2.mp4").exists()
    story = project.root / "stories" / "approved" / "20261120-001.json"
    assert read(story)["history"][-1]["file"] == "rejected/20261120-001-2.mp4"


def test_reject_video_drop_moves_story(project):
    put_story(project, "approved")
    put_video(project, "upload")
    library.reject_video(project, "20261120-001", "r", "i", remake=False, today=DAY)
    assert (project.root / "stories" / "rejected" / "20261120-001.json").exists()
    assert not (project.root / "stories" / "approved" / "20261120-001.json").exists()


def test_status_and_rejections(project):
    put_story(project, "draft", "a")
    put_story(project, "approved", "b")
    put_video(project, "ready", "b")
    put_story(project, "approved", "c")
    put_video(project, "upload", "c")
    put_story(project, "approved", "d")
    put_story(project, "rejected", "e", history=[
        {"date": "2026-11-19", "event": "video_rejected", "reason": "R", "idea": "I", "file": "rejected/e-1.mp4"}])
    states = {r.id: r.state for r in library.status(project)}
    assert states == {"a": "物語CHECK待ち", "b": "動画CHECK待ち", "c": "投稿待ち",
                      "d": "動画づくり待ち", "e": "ボツ（動画）"}
    [r] = library.rejections(project)
    assert (r.id, r.stage, r.reason, r.idea) == ("e", "動画", "R", "I")


def test_story_in_two_places_is_an_error(project):
    put_story(project, "draft")
    put_story(project, "approved")
    with pytest.raises(AiShortsError, match="複数"):
        library.find_story(project, "20261120-001")


def test_all_approved_skips_existing_videos(project, monkeypatch, capsys):
    (project.root / "config.example.yaml").write_text("", encoding="utf-8")
    (project.root / "config.yaml").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("AI_SHORTS_ROOT", str(project.root))
    put_story(project, "approved", "b")
    put_video(project, "ready", "b")
    put_story(project, "approved", "c")
    ran = []
    import ai_shorts.cli as cli
    monkeypatch.setattr(cli, "STAGES", {"x": lambda p, sid: ran.append(sid)})
    assert main(["all", "--approved"]) == 0
    assert ran == ["c"]
    assert "スキップ（b）" in capsys.readouterr().out
