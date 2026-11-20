"""YouTube Data API の薄いラッパー（ログインと動画のアップロードだけ）。

google-api-python-client と google-auth-oauthlib は、使うときにだけ読み込む
（ほかの工程はこれらがなくても動く）。認証情報は config.yaml の youtube.client_secret /
youtube.token の場所に置き、git には入れない（docs/runbook.md 3-6）。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from .config import Project
from .errors import ConfigError, ExternalToolError

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
_RETRY_STATUS = {500, 502, 503, 504}
_MAX_RETRIES = 5
_CHUNK = 8 * 1024 * 1024


def _require_libs():
    try:
        from google.auth.exceptions import RefreshError
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload
    except ImportError as e:
        raise ExternalToolError(
            "YouTube への投稿に使うパッケージが入っていません。"
            r"`.venv\Scripts\python -m pip install -r requirements.txt` を実行してください。"
        ) from e
    return {
        "RefreshError": RefreshError, "Request": Request, "Credentials": Credentials,
        "InstalledAppFlow": InstalledAppFlow, "build": build, "HttpError": HttpError,
        "MediaFileUpload": MediaFileUpload,
    }


def _paths(project: Project) -> tuple[Path, Path]:
    return project.path(project.get("youtube.client_secret")), project.path(project.get("youtube.token"))


def login(project: Project, *, interactive: bool = True, force: bool = False):
    """保存したトークンを読み、切れていれば更新する。なければブラウザでログインする。"""
    lib = _require_libs()
    secret, token = _paths(project)
    creds = None
    if token.exists() and not force:
        creds = lib["Credentials"].from_authorized_user_file(str(token), SCOPES)
        if creds.valid:
            return creds
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(lib["Request"]())
                token.write_text(creds.to_json(), encoding="utf-8")
                return creds
            except lib["RefreshError"]:
                creds = None
    if not interactive:
        raise ExternalToolError(
            "YouTube のログインが切れています。`python -m ai_shorts youtube-login` でログインし直してください。")
    if not secret.exists():
        raise ConfigError(
            f"{secret} がありません。Google Cloud で作った OAuth クライアント（デスクトップアプリ）の"
            "JSON をここに置いてください（docs/runbook.md 3-6）。")
    flow = lib["InstalledAppFlow"].from_client_secrets_file(str(secret), SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text(creds.to_json(), encoding="utf-8")
    return creds


def make_uploader(project: Project) -> Callable[[Path, dict, Callable[[float], None]], dict]:
    """(動画のパス, videos.insert の body, 進み具合の表示) → YouTube の応答（videos リソース）"""
    lib = _require_libs()
    creds = login(project, interactive=True)
    service = lib["build"]("youtube", "v3", credentials=creds, cache_discovery=False)
    HttpError = lib["HttpError"]

    def upload(video: Path, body: dict, on_progress: Callable[[float], None]) -> dict:
        media = lib["MediaFileUpload"](str(video), mimetype="video/mp4", chunksize=_CHUNK, resumable=True)
        request = service.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        retries = 0
        while response is None:
            try:
                status, response = request.next_chunk()
            except HttpError as e:
                code = getattr(e.resp, "status", 0)
                if code in _RETRY_STATUS and retries < _MAX_RETRIES:
                    retries += 1
                    time.sleep(2 ** retries)
                    continue
                raise ExternalToolError(f"YouTube への投稿に失敗しました（{code}）: {_reason(e)}") from e
            except OSError as e:
                if retries < _MAX_RETRIES:
                    retries += 1
                    time.sleep(2 ** retries)
                    continue
                raise ExternalToolError(f"YouTube に接続できません: {e}") from e
            if status is not None:
                on_progress(status.progress())
        return response

    return upload


def _reason(e) -> str:
    details = getattr(e, "error_details", None)
    if isinstance(details, list) and details:
        d = details[0]
        if isinstance(d, dict):
            return f"{d.get('reason', '')} {d.get('message', '')}".strip()
    return str(getattr(e, "reason", "") or e)
