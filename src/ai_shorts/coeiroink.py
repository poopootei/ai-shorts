"""COEIROINK v2 エンジンの薄いラッパー。

tts からは VOICEVOX と同じ形（audio_query → synthesis）で呼べるようにする。
話者はスタイル ID（整数）で指定し、話者の UUID はエンジンの /v1/speakers から引く。
"""

from __future__ import annotations

from typing import Any

import requests

from .errors import ExternalToolError

_SMALL_KANA = set("ァィゥェォャュョヮ")


def count_moras(katakana: str) -> int:
    """カタカナのモーラ数。小さいァィゥェォャュョは前の字とあわせて1モーラ（ッ・ン・ーは1モーラ）。"""
    return sum(1 for c in katakana if c not in _SMALL_KANA)


class CoeiroinkClient:
    def __init__(self, url: str, timeout: float = 180.0):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._style_to_speaker: dict[int, str] | None = None

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        try:
            resp = self._session.request(method, f"{self.url}{path}", timeout=self.timeout, **kwargs)
        except requests.ConnectionError as e:
            raise ExternalToolError(
                f"COEIROINK エンジンに接続できません（{self.url}）。"
                "tools/coeiroink/engine/engine.exe を起動してから再実行してください。"
            ) from e
        except requests.Timeout as e:
            raise ExternalToolError(f"COEIROINK エンジンが応答しません（{path}）。") from e
        if not resp.ok:
            raise ExternalToolError(
                f"COEIROINK がエラーを返しました（{path}, {resp.status_code}）: {resp.text[:300]}"
            )
        return resp

    def speakers(self) -> list[dict[str, Any]]:
        return self._request("GET", "/v1/speakers").json()

    def speaker_uuid(self, style_id: int) -> str:
        if self._style_to_speaker is None:
            self._style_to_speaker = {
                st["styleId"]: sp["speakerUuid"] for sp in self.speakers() for st in sp["styles"]
            }
        if style_id not in self._style_to_speaker:
            raise ExternalToolError(
                f"COEIROINK にスタイル ID {style_id} の話者が入っていません。"
                f"入っているスタイル: {sorted(self._style_to_speaker)}"
            )
        return self._style_to_speaker[style_id]

    def set_dictionary(self, words: list[dict[str, Any]]) -> None:
        """ユーザー辞書をまるごと置き換える（エンジンは保存しないので、起動のたびに送る）。"""
        body = {"dictionaryWords": [
            {"word": w["surface"], "yomi": w["pronunciation"], "accent": w["accent_type"],
             "numMoras": count_moras(w["pronunciation"])}
            for w in words
        ]}
        self._request("POST", "/v1/set_dictionary", json=body)

    def reading(self, text: str) -> str:
        """読みの確認用。アクセント句ごとにひらがなを / でつなぐ。"""
        detail = self._request("POST", "/v1/estimate_prosody", json={"text": text}).json()["detail"]
        return "/".join("".join(m["hira"] for m in phrase) for phrase in detail)

    # ---- VOICEVOX と同じ形のインターフェース ----

    def audio_query(self, text: str, speaker: int) -> dict[str, Any]:
        prosody = self._request("POST", "/v1/estimate_prosody", json={"text": text}).json()
        return {"text": text, "prosodyDetail": prosody["detail"], "kana": prosody.get("plain")}

    def synthesis(self, query: dict[str, Any], speaker: int) -> bytes:
        body = {
            "speakerUuid": self.speaker_uuid(speaker),
            "styleId": speaker,
            "text": query["text"],
            "prosodyDetail": query["prosodyDetail"],
            "speedScale": query.get("speedScale", 1.0),
            "volumeScale": query.get("volumeScale", 1.0),
            "pitchScale": query.get("pitchScale", 0.0),
            "intonationScale": query.get("intonationScale", 1.0),
            "prePhonemeLength": query.get("prePhonemeLength", 0.1),
            "postPhonemeLength": query.get("postPhonemeLength", 0.1),
            "outputSamplingRate": query.get("outputSamplingRate", 48000),
        }
        return self._request("POST", "/v1/synthesis", json=body).content
