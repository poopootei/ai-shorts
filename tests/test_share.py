import datetime as dt
import importlib.util
import json
import subprocess
import threading
import urllib.request
from pathlib import Path

import pytest

from ai_shorts import share
from ai_shorts.config import Project

JST = dt.timezone(dt.timedelta(hours=9))
MORNING = dt.datetime(2026, 11, 20, 10, 0, tzinfo=JST)
SHARE = {"host": "lenovo", "remote_dir": "projects/ai-shorts-share", "port": 8040, "url": "http://minipc:8040/"}
YT = {"publish_time": "18:00", "utc_offset": "+09:00", "min_lead_minutes": 60}

spec = importlib.util.spec_from_file_location(
    "share_server", Path(__file__).resolve().parents[1] / "share_app" / "server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


def make_project(tmp_path, youtube=True):
    config = {"share": dict(SHARE)}
    if youtube:
        config["youtube"] = dict(YT)
    return Project(root=tmp_path, config=config)


def ready(project, sid, title="題", size=3):
    d = project.root / "stories" / "approved"
    d.mkdir(parents=True, exist_ok=True)
    data = {"id": sid, "title": title, "tags": ["ショートショート", "朗読"], "approved": True}
    (d / f"{sid}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    up = project.root / "upload"
    up.mkdir(exist_ok=True)
    (up / f"{sid}.mp4").write_bytes(b"x" * size)
    (up / f"{sid}.txt").write_text(f"{title}\n\n説明\n", encoding="utf-8")


# --- このPC側 -----------------------------------------------------------

def test_build_items_has_copy_texts_and_schedule(tmp_path):
    project = make_project(tmp_path)
    ready(project, "20261121-004", "外れない天気予報")
    ready(project, "20261121-005", "駅前の占い師")
    items = share.build_items(project, MORNING)
    assert [i["id"] for i in items] == ["20261121-004", "20261121-005"]
    assert items[0]["title"] == "外れない天気予報"
    assert items[0]["description"] == "外れない天気予報\n\n説明"
    assert items[0]["tags"] == ["ショートショート", "朗読"]
    assert items[0]["publish_at"] == "2026-11-20（金）18:00"
    assert items[1]["publish_at"] == "2026-11-21（土）18:00"


def test_build_items_without_youtube_config_has_no_schedule(tmp_path):
    project = make_project(tmp_path, youtube=False)
    ready(project, "20261121-004")
    assert share.build_items(project, MORNING)[0]["publish_at"] == ""


def test_plan_sync_sends_new_or_changed_and_removes_gone():
    send, remove = share.plan_sync({"a": 10, "b": 20, "c": 30},
                                   {"a": {"size": 10}, "b": {"size": 99}, "old": {"size": 5}, "bad id!": {}})
    assert send == ["b", "c"]
    assert remove == ["old"]


class FakeSsh:
    def __init__(self, remote):
        self.remote = remote
        self.calls = []

    def __call__(self, cmd, input=None, capture_output=True, timeout=None):
        self.calls.append((cmd, input))
        out = json.dumps(self.remote).encode() if cmd[-2:] == ["-", SHARE["remote_dir"]] else b""
        return subprocess.CompletedProcess(cmd, 0, out, b"")


def test_sync_sends_video_meta_and_reports_marks(tmp_path, capsys):
    project = make_project(tmp_path)
    ready(project, "20261121-004", size=3)
    ready(project, "20261121-005", size=4)
    fake = FakeSsh({"20261121-004": {"size": 3, "done": {"date": "2026-11-21"}},
                    "20261120-001": {"size": 9, "done": None}})
    share.sync(project, MORNING, run=fake)
    remote_cmds = [c[-1] for c, _ in fake.calls]
    # 004 は同じ大きさなので動画は送らない。005 は送る。meta は両方
    assert not any("20261121-004/video.mp4" in c for c in remote_cmds)
    assert any("20261121-005/video.mp4.part" in c for c in remote_cmds)
    assert sum("meta.json" in c for c in remote_cmds) == 2
    # upload/ にない 20261120-001 は消す
    assert any(c[-1] == "20261120-001" for c, _ in fake.calls)
    meta = next(json.loads(i) for c, i in fake.calls if "20261121-005/meta.json" in c[-1])
    assert meta["title"] == "題"
    out = capsys.readouterr().out
    assert "タブレットで「上げた」: 20261121-004（2026-11-21）" in out


def test_sync_reports_ssh_failure(tmp_path):
    project = make_project(tmp_path)

    def broken(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 255, b"", b"Connection refused")

    with pytest.raises(share.AiShortsError, match="Connection refused"):
        share.sync(project, MORNING, run=broken)


def test_settings_reject_unsafe_remote_dir(tmp_path):
    project = make_project(tmp_path)
    project.config["share"]["remote_dir"] = "../etc; rm -rf ~"
    with pytest.raises(share.ConfigError):
        share.sync(project, MORNING, run=FakeSsh({}))


def test_unit_file_runs_server_on_port():
    unit = share.unit_file("projects/ai-shorts-share", 8040)
    assert "ExecStart=/usr/bin/python3 %h/projects/ai-shorts-share/server.py --port 8040" in unit


# --- MiniPC 側（share_app/server.py）--------------------------------------

def test_parse_range():
    assert server.parse_range("bytes=0-", 100) == (0, 99)
    assert server.parse_range("bytes=10-19", 100) == (10, 19)
    assert server.parse_range("bytes=-10", 100) == (90, 99)
    assert server.parse_range("bytes=90-500", 100) == (90, 99)
    assert server.parse_range("bytes=200-", 100) is None
    assert server.parse_range(None, 100) is None


def test_render_page_escapes_text():
    page = server.render_page([{"id": "a", "title": "<b>題</b>", "description": "説明", "tags": [],
                                "publish_at": "", "done": None, "size_mb": 1.0}])
    assert "&lt;b&gt;題&lt;/b&gt;" in page
    assert "<b>題</b>" not in page


@pytest.fixture
def running(tmp_path):
    d = tmp_path / "data" / "20261121-004"
    d.mkdir(parents=True)
    (d / "video.mp4").write_bytes(bytes(range(100)))
    (d / "meta.json").write_text(json.dumps({"title": "外れない天気予報", "description": "説明",
                                             "tags": ["朗読"], "publish_at": ""}), encoding="utf-8")
    srv = server.make_server(0, tmp_path / "data")
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", d
    srv.shutdown()


def test_server_lists_and_streams_ranges(running):
    base, _ = running
    page = urllib.request.urlopen(base + "/").read().decode("utf-8")
    assert "外れない天気予報" in page and "v/20261121-004.mp4" in page
    req = urllib.request.Request(base + "/v/20261121-004.mp4", headers={"Range": "bytes=10-19"})
    with urllib.request.urlopen(req) as r:
        assert r.status == 206
        assert r.headers["Content-Range"] == "bytes 10-19/100"
        assert r.read() == bytes(range(10, 20))
    with urllib.request.urlopen(base + "/dl/20261121-004.mp4") as r:
        assert "attachment" in r.headers["Content-Disposition"]
        assert len(r.read()) == 100


def test_server_marks_done(running):
    base, d = running
    req = urllib.request.Request(base + "/api/done/20261121-004", data=b'{"done": true}', method="POST",
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req)
    assert json.loads((d / "done.json").read_text(encoding="utf-8"))["date"]
    assert "上げた" in urllib.request.urlopen(base + "/").read().decode("utf-8")
    req = urllib.request.Request(base + "/api/done/20261121-004", data=b'{"done": false}', method="POST")
    urllib.request.urlopen(req)
    assert not (d / "done.json").exists()
