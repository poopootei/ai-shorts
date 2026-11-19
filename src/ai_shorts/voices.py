"""声の選び方とエンジンへの接続。

config の voices に「声」を登録しておき、物語 JSON の "voice"（なければ tts.default_voice）で選ぶ。
エンジンは type が voicevox（VOICEVOX / AivisSpeech）か coeiroink。
どのエンジンにも assets/tts/user_dict.yaml の読み・アクセントを反映してから使う。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from . import userdict
from .coeiroink import CoeiroinkClient
from .config import Project
from .errors import ConfigError
from .voicevox import VoicevoxClient

ENGINE_TYPES = {"voicevox", "coeiroink"}


@dataclass(frozen=True)
class Voice:
    key: str
    engine: str
    engine_type: str
    url: str
    style_id: int
    credit: str
    speed: float
    speed_max: float
    intonation_scale: float


def resolve(project: Project, voice_key: str | None) -> Voice:
    key = voice_key or project.get("tts.default_voice")
    voices = project.get("voices")
    if key not in voices:
        raise ConfigError(f"声 {key!r} が config.yaml の voices にありません。登録済み: {sorted(voices)}")
    v = voices[key]
    engine = v.get("engine")
    eng = project.get(f"engines.{engine}", None)
    if not eng:
        raise ConfigError(f"声 {key} のエンジン {engine!r} が config.yaml の engines にありません。")
    if eng.get("type") not in ENGINE_TYPES:
        raise ConfigError(f"エンジン {engine} の type は {sorted(ENGINE_TYPES)} のどれかにしてください。")
    if not v.get("credit"):
        raise ConfigError(f"声 {key} に credit（クレジット表記）がありません。")
    return Voice(
        key=key,
        engine=engine,
        engine_type=eng["type"],
        url=eng["url"],
        style_id=int(v["style_id"]),
        credit=str(v["credit"]),
        speed=float(v.get("speed", project.get("tts.speed"))),
        speed_max=float(v.get("speed_max", project.get("tts.speed_max"))),
        intonation_scale=float(v.get("intonation_scale", 1.0)),
    )


def connect(voice: Voice, words: list[dict[str, Any]], log: Callable[[str], None]):
    """エンジンのクライアントを作り、ユーザー辞書を反映して返す。"""
    if voice.engine_type == "coeiroink":
        client: Any = CoeiroinkClient(voice.url)
        client.set_dictionary(words)
        log(f"{voice.engine}: ユーザー辞書 {len(words)} 語を反映")
    else:
        client = VoicevoxClient(voice.url)
        added, updated, deleted = userdict.sync(client, words)
        log(f"{voice.engine}: ユーザー辞書 {len(words)} 語（追加 {added}, 更新 {updated}, 削除 {deleted}）")
    return client
