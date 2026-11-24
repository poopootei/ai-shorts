from pathlib import Path

import pytest

from ai_shorts.coeiroink import count_moras
from ai_shorts.config import Project
from ai_shorts.errors import ConfigError
from ai_shorts.qa import describe
from ai_shorts.story import Story
from ai_shorts.voices import resolve

CONFIG = {
    "tts": {"default_voice": "ofutonp", "speed": 1.0, "speed_max": 1.15},
    "engines": {
        "coeiroink": {"type": "coeiroink", "url": "http://127.0.0.1:50032"},
        "aivisspeech": {"type": "voicevox", "url": "http://127.0.0.1:10101"},
    },
    "voices": {
        "ofutonp": {"engine": "coeiroink", "style_id": 2, "credit": "COEIROINK:おふとんP"},
        "aida": {"engine": "aivisspeech", "style_id": 1310138976, "credit": "AivisSpeech:阿井田 茂",
                 "speed": 0.95},
        "broken": {"engine": "nothing", "style_id": 1, "credit": "x"},
    },
}


def project():
    return Project(root=Path("."), config=CONFIG)


def test_resolve_default_and_named_voice():
    v = resolve(project(), None)
    assert (v.key, v.engine_type, v.style_id, v.credit) == ("ofutonp", "coeiroink", 2, "COEIROINK:おふとんP")
    assert (v.speed, v.speed_max) == (1.0, 1.15)
    a = resolve(project(), "aida")
    assert (a.engine_type, a.url, a.speed) == ("voicevox", "http://127.0.0.1:10101", 0.95)


def test_resolve_errors_are_clear():
    with pytest.raises(ConfigError, match="voices にありません"):
        resolve(project(), "unknown")
    with pytest.raises(ConfigError, match="engines にありません"):
        resolve(project(), "broken")


def test_count_moras():
    assert count_moras("コベヤ") == 3
    assert count_moras("カンコーヒー") == 6
    assert count_moras("タンジョウビ") == 5


def test_description_uses_voice_credit():
    s = Story(id="x", title="題", hook="引き", body="本文", tags=["朗読"])
    text = describe(s, "COEIROINK:おふとんP", None)
    assert "声：COEIROINK:おふとんP" in text and "#朗読" in text
    assert "出典" not in text


def test_description_uses_visual_credit_instead_of_images():
    s = Story(id="x", title="題", hook="引き", body="本文")
    images = {"images": [{"source": "openverse", "license": "cc0"}]}
    text = describe(s, "COEIROINK:おふとんP", images, visual={"kind": "3d", "credit": "3D（Blender）"})
    assert "映像：3D（Blender）" in text and "背景画像" not in text
    assert "背景画像：CC0（openverse）" in describe(s, "COEIROINK:おふとんP", images)


def test_description_shows_source():
    s = Story(id="x", title="題", hook="引き", body="本文", source="芥川龍之介『蜘蛛の糸』（青空文庫）")
    text = describe(s, "COEIROINK:おふとんP", None)
    assert "出典：芥川龍之介『蜘蛛の糸』（青空文庫）" in text
