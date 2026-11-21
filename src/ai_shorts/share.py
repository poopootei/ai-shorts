"""受け渡し（share）: upload/ の投稿待ちを MiniPC に送り、タブレットから保存・コピーできるようにする。

MiniPC では share_app/server.py（標準ライブラリだけの Web アプリ）が systemd --user で動く（D-016）。
送るのは ssh だけ（~/.ssh/config の Host 名）。scp は Windows でドライブ名を接続先と取り違えるので使わず、
標準入力で流し込む。upload/ にないもの（投稿済み・ボツ）は MiniPC から消す。

    python -m ai_shorts share            # 送る（同じ大きさの動画は送り直さない）
    python -m ai_shorts share --install  # 初回・server.py を変えたとき：サーバーを置いて起動し直す
"""

from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
from pathlib import Path
from typing import Callable

from . import upload
from .config import Project
from .errors import AiShortsError, ConfigError

ID_RE = re.compile(r"[A-Za-z0-9_-]+")
SERVICE = "ai-shorts-share"
WEEKDAYS = "月火水木金土日"

Runner = Callable[..., subprocess.CompletedProcess]

# MiniPC で python3 - <remote_dir> として動かす。data/ の一覧（動画の大きさと「上げた」の印）を JSON で返す。
REMOTE_LIST = r"""
import json, sys
from pathlib import Path
data = Path.home() / sys.argv[1] / "data"
data.mkdir(parents=True, exist_ok=True)
out = {}
for d in sorted(data.iterdir()):
    if d.is_dir():
        v, done = d / "video.mp4", d / "done.json"
        out[d.name] = {"size": v.stat().st_size if v.exists() else 0,
                       "done": json.loads(done.read_text(encoding="utf-8")) if done.exists() else None}
print(json.dumps(out))
"""

# python3 - <remote_dir> <id> ... : data/<id> を消す
REMOTE_REMOVE = r"""
import re, shutil, sys
from pathlib import Path
data = Path.home() / sys.argv[1] / "data"
for i in sys.argv[2:]:
    if re.fullmatch(r"[A-Za-z0-9_-]+", i) and (data / i).is_dir():
        shutil.rmtree(data / i)
"""


def log(msg: str) -> None:
    print(f"[share] {msg}")


def _settings(project: Project) -> tuple[str, str, int, str]:
    host = str(project.get("share.host"))
    remote_dir = str(project.get("share.remote_dir")).strip("/")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", host):
        raise ConfigError(f"share.host は ~/.ssh/config の Host 名で書いてください（いまは {host!r}）。")
    if not re.fullmatch(r"[A-Za-z0-9_./-]+", remote_dir) or ".." in remote_dir.split("/"):
        raise ConfigError(f"share.remote_dir は MiniPC のホームからの相対パスで書いてください（いまは {remote_dir!r}）。")
    return host, remote_dir, int(project.get("share.port")), str(project.get("share.url"))


def _ssh(run: Runner, host: str, command: list[str], data: bytes | None = None, timeout: int = 120) -> str:
    try:
        r = run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, *command],
                input=data, capture_output=True, timeout=timeout)
    except FileNotFoundError as e:
        raise AiShortsError("ssh が見つかりません（Windows の OpenSSH クライアントか Git Bash が要ります）。") from e
    except subprocess.TimeoutExpired as e:
        raise AiShortsError(f"{host} への ssh が {timeout} 秒で終わりませんでした。MiniPC が起きているか見てください。") from e
    if r.returncode != 0:
        err = r.stderr.decode("utf-8", "replace").strip()
        raise AiShortsError(f"{host} に ssh で接続できないか、MiniPC 側で失敗しました: {err}")
    return r.stdout.decode("utf-8", "replace")


def format_when(when: dt.datetime) -> str:
    return f"{when:%Y-%m-%d}（{WEEKDAYS[when.weekday()]}）{when:%H:%M}"


def build_items(project: Project, now: dt.datetime) -> list[dict]:
    """upload/ の投稿待ちごとの meta.json の中身。

    予約の日時の目安は upload と同じ決め方（1 日 1 本）。config.yaml に youtube: がなければ出さない。
    """
    plans = [upload.make_plan(project, i) for i in upload.pending_ids(project)]
    try:
        whens: list[dt.datetime | None] = list(upload.schedule(project, len(plans), now)) if plans else []
    except ConfigError:
        whens = [None] * len(plans)
    return [{
        "id": plan.id,
        "title": plan.title,
        "description": plan.description,
        "tags": plan.tags,
        "publish_at": format_when(when) if when else "",
    } for plan, when in zip(plans, whens)]


def plan_sync(local_sizes: dict[str, int], remote: dict[str, dict]) -> tuple[list[str], list[str]]:
    """(動画を送るもの, MiniPC から消すもの)。大きさが同じ動画は送り直さない。"""
    send = [i for i, size in local_sizes.items() if remote.get(i, {}).get("size") != size]
    remove = [i for i in remote if i not in local_sizes and ID_RE.fullmatch(i)]
    return send, remove


def _put(run: Runner, host: str, remote_path: str, data: bytes, timeout: int = 120) -> None:
    """remote_path に data を書く（途中で切れても壊れた mp4 が残らないよう、.part に書いてから置き換える）。"""
    parent = remote_path.rsplit("/", 1)[0]
    _ssh(run, host, [f"mkdir -p {parent} && cat > {remote_path}.part && mv {remote_path}.part {remote_path}"],
         data, timeout)


def sync(project: Project, now: dt.datetime | None = None, run: Runner = subprocess.run) -> None:
    host, remote_dir, _, url = _settings(project)
    items = build_items(project, now or dt.datetime.now(dt.timezone.utc))
    remote = json.loads(_ssh(run, host, ["python3", "-", remote_dir], REMOTE_LIST.encode("utf-8")) or "{}")
    local_sizes = {it["id"]: (project.root / "upload" / f"{it['id']}.mp4").stat().st_size for it in items}
    send, remove = plan_sync(local_sizes, remote)
    for it in items:
        base = f"{remote_dir}/data/{it['id']}"
        if it["id"] in send:
            log(f"{it['id']}「{it['title']}」動画を送る（{local_sizes[it['id']] / 1e6:.1f} MB）")
            video = (project.root / "upload" / f"{it['id']}.mp4").read_bytes()
            _put(run, host, f"{base}/video.mp4", video, timeout=600)
        _put(run, host, f"{base}/meta.json", json.dumps(it, ensure_ascii=False, indent=2).encode("utf-8"))
    if remove:
        _ssh(run, host, ["python3", "-", remote_dir, *remove], REMOTE_REMOVE.encode("utf-8"))
        log(f"upload/ にないので MiniPC から消した: {', '.join(remove)}")
    log(f"投稿待ち {len(items)} 本（動画を送ったもの {len(send)} 本）→ {url}")
    marked = [(i, remote[i]["done"]) for i in local_sizes if remote.get(i, {}).get("done")]
    for i, done in marked:
        log(f"タブレットで「上げた」: {i}（{done.get('date', '')}）→ posted で記録する")


def unit_file(remote_dir: str, port: int) -> str:
    base = f"%h/{remote_dir}"
    return f"""[Unit]
Description=ai-shorts 投稿待ちの受け渡し（LAN専用。タブレットで動画を保存し、タイトル・説明文をコピーする）
After=network.target

[Service]
WorkingDirectory={base}
ExecStart=/usr/bin/python3 {base}/server.py --port {port} --data {base}/data
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""


def install(project: Project, run: Runner = subprocess.run) -> None:
    """server.py と systemd --user のユニットを置いて、起動し直す。"""
    host, remote_dir, port, url = _settings(project)
    server = Path(__file__).resolve().parents[2] / "share_app" / "server.py"
    if not server.exists():
        raise AiShortsError(f"{server} がありません。")
    _put(run, host, f"{remote_dir}/server.py", server.read_bytes())
    _put(run, host, f".config/systemd/user/{SERVICE}.service", unit_file(remote_dir, port).encode("utf-8"))
    _ssh(run, host, [f"systemctl --user daemon-reload && systemctl --user enable {SERVICE} "
                     f"&& systemctl --user restart {SERVICE} && sleep 1 && systemctl --user is-active {SERVICE}"])
    log(f"{host} で {SERVICE} を起動しました → {url}")
