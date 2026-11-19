import pytest

from ai_shorts.errors import ConfigError
from ai_shorts.userdict import load, sync


class FakeDict:
    def __init__(self, words):
        self.words = dict(words)
        self.calls = []

    def user_dict(self):
        return dict(self.words)

    def add_word(self, word):
        self.calls.append(("add", word["surface"]))
        uuid = f"u{len(self.words)}"
        self.words[uuid] = dict(word, surface=word["surface"])
        return uuid

    def update_word(self, uuid, word):
        self.calls.append(("update", word["surface"]))
        self.words[uuid] = dict(word)

    def delete_word(self, uuid):
        self.calls.append(("delete", self.words[uuid]["surface"]))
        del self.words[uuid]


W = {"pronunciation": "カンコーヒー", "accent_type": 3, "word_type": "COMMON_NOUN", "priority": 5}


def test_sync_adds_updates_and_deletes():
    engine = FakeDict({
        "a": {"surface": "缶コーヒー", "pronunciation": "カンコーヒー", "accent_type": 0, "priority": 5},
        "b": {"surface": "古い語", "pronunciation": "フルイゴ", "accent_type": 0, "priority": 5},
    })
    wanted = [dict(W, surface="缶コーヒー"),
              {"surface": "補充", "pronunciation": "ホジュウ", "accent_type": 0,
               "word_type": "COMMON_NOUN", "priority": 5}]
    assert sync(engine, wanted) == (1, 1, 1)
    assert sorted(engine.calls) == [("add", "補充"), ("delete", "古い語"), ("update", "缶コーヒー")]
    engine.calls.clear()
    assert sync(engine, wanted) == (0, 0, 0)


def test_sync_matches_engine_fullwidth_surface():
    engine = FakeDict({"a": {"surface": "ＶＯＩＣＥ", "pronunciation": "ボイス", "accent_type": 1, "priority": 5}})
    assert sync(engine, [{"surface": "VOICE", "pronunciation": "ボイス", "accent_type": 1,
                          "word_type": "COMMON_NOUN", "priority": 5}]) == (0, 0, 0)


def test_load_validates(tmp_path):
    p = tmp_path / "d.yaml"
    p.write_text("- surface: 補充\n  pronunciation: ホジュウ\n  accent_type: 0\n", encoding="utf-8")
    assert load(p)[0]["word_type"] == "COMMON_NOUN"
    p.write_text("- surface: 補充\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load(p)
    assert load(tmp_path / "none.yaml") == []
