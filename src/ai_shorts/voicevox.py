"""VOICEVOX エンジンの薄いラッパー。"""

from __future__ import annotations

from typing import Any

import requests

from .errors import ExternalToolError


class VoicevoxClient:
    def __init__(self, url: str, timeout: float = 120.0):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        try:
            resp = self._session.request(
                method, f"{self.url}{path}", timeout=self.timeout, **kwargs
            )
        except requests.ConnectionError as e:
            raise ExternalToolError(
                f"VOICEVOX エンジンに接続できません（{self.url}）。"
                "VOICEVOX を起動してから再実行してください。"
            ) from e
        except requests.Timeout as e:
            raise ExternalToolError(f"VOICEVOX エンジンが応答しません（{path}）。") from e
        if not resp.ok:
            raise ExternalToolError(
                f"VOICEVOX がエラーを返しました（{path}, {resp.status_code}）: {resp.text[:300]}"
            )
        return resp

    def version(self) -> str:
        return self._request("GET", "/version").json()

    def audio_query(self, text: str, speaker: int) -> dict[str, Any]:
        return self._request(
            "POST", "/audio_query", params={"text": text, "speaker": speaker}
        ).json()

    def synthesis(self, query: dict[str, Any], speaker: int) -> bytes:
        return self._request(
            "POST", "/synthesis", params={"speaker": speaker}, json=query
        ).content

    # ---- ユーザー辞書 ----

    def user_dict(self) -> dict[str, dict[str, Any]]:
        return self._request("GET", "/user_dict").json()

    def add_word(self, word: dict[str, Any]) -> str:
        return self._request("POST", "/user_dict_word", params=word).json()

    def update_word(self, uuid: str, word: dict[str, Any]) -> None:
        self._request("PUT", f"/user_dict_word/{uuid}", params=word)

    def delete_word(self, uuid: str) -> None:
        self._request("DELETE", f"/user_dict_word/{uuid}")
