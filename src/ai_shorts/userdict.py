"""読みとアクセントの辞書。assets/ の YAML を正とし、tts のたびにエンジンのユーザー辞書をそろえる。

エンジン（tools/voicevox_engine）はこのプロジェクト専用なので、YAML にない語はエンジンから消す。
"""

from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Any, Protocol

import yaml

from .errors import ConfigError

WORD_TYPES = {"PROPER_NOUN", "COMMON_NOUN", "VERB", "ADJECTIVE", "SUFFIX"}


class DictClient(Protocol):
    def user_dict(self) -> dict[str, dict[str, Any]]: ...
    def add_word(self, word: dict[str, Any]) -> str: ...
    def update_word(self, uuid: str, word: dict[str, Any]) -> None: ...
    def delete_word(self, uuid: str) -> None: ...


def _zenkaku(s: str) -> str:
    """エンジンは表記を全角にして保存するので、比べる前にそろえる。"""
    return "".join(chr(ord(c) + 0xFEE0) if "!" <= c <= "~" else c for c in unicodedata.normalize("NFKC", s))


def load(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    words = []
    for i, e in enumerate(entries, start=1):
        try:
            word = {
                "surface": str(e["surface"]),
                "pronunciation": str(e["pronunciation"]),
                "accent_type": int(e["accent_type"]),
                "word_type": str(e.get("word_type", "COMMON_NOUN")),
                "priority": int(e.get("priority", 5)),
            }
        except (KeyError, TypeError, ValueError) as err:
            raise ConfigError(f"{path} の {i} 件目が正しくありません: {err}") from err
        if word["word_type"] not in WORD_TYPES:
            raise ConfigError(f"{path} の {i} 件目: word_type は {sorted(WORD_TYPES)} のどれか")
        words.append(word)
    return words


def sync(client: DictClient, words: list[dict[str, Any]]) -> tuple[int, int, int]:
    """エンジンの辞書を words と同じにする。戻り値は（追加, 更新, 削除）の件数。"""
    current = {_zenkaku(w["surface"]): (uuid, w) for uuid, w in client.user_dict().items()}
    wanted = {_zenkaku(w["surface"]): w for w in words}
    added = updated = deleted = 0
    for surface, word in wanted.items():
        if surface not in current:
            client.add_word(word)
            added += 1
            continue
        uuid, have = current[surface]
        same = (have.get("pronunciation") == word["pronunciation"]
                and have.get("accent_type") == word["accent_type"]
                and have.get("priority") == word["priority"])
        if not same:
            client.update_word(uuid, word)
            updated += 1
    for surface, (uuid, _) in current.items():
        if surface not in wanted:
            client.delete_word(uuid)
            deleted += 1
    return added, updated, deleted
