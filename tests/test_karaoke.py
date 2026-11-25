import numpy as np

from ai_shorts.karaoke import Speech, char_times, char_weight, find_speech
from ai_shorts.subs import build_events, to_ass

SR = 1000


def tone(seconds: float) -> np.ndarray:
    return np.full(int(seconds * SR), 0.5, dtype=np.float32) * np.sign(np.sin(np.arange(int(seconds * SR))))


def silence(seconds: float) -> np.ndarray:
    return np.zeros(int(seconds * SR), dtype=np.float32)


def test_char_weight():
    assert char_weight("あ") == 1.0
    assert char_weight("ゃ") == 0.0
    assert char_weight("、") == 0.0
    assert char_weight("朝") > 1.0


def test_find_speech_trims_edges_and_finds_pause():
    audio = np.concatenate([silence(0.1), tone(1.0), silence(0.3), tone(1.0), silence(0.1)])
    sp = find_speech(audio, SR, 0.0, len(audio) / SR)
    assert abs(sp.start - 0.1) < 0.02
    assert abs(sp.end - 2.4) < 0.02
    assert len(sp.gaps) == 1
    assert abs(sp.gaps[0][0] - 1.1) < 0.02 and abs(sp.gaps[0][1] - 1.4) < 0.02


def test_char_times_anchor_comma_to_pause():
    # 「あいう、えお」：読点の位置に間（1.1〜1.4秒）がある
    sp = Speech(0.1, 2.4, [(1.1, 1.4)])
    t = char_times("あいう、えお", sp)
    assert abs(t[0][0] - 0.1) < 1e-6
    assert abs(t[2][1] - 1.1) < 1e-6      # 「う」は間の前で読み終わる
    assert t[3][0] == t[3][1]             # 読点は長さ0
    assert abs(t[4][0] - 1.4) < 1e-6      # 「え」は間のあとから
    assert abs(t[5][1] - 2.4) < 1e-6


def test_char_times_without_pause_spreads_over_speech():
    t = char_times("あい、う", Speech(0.0, 3.0, []))
    assert abs(t[-1][1] - 3.0) < 1e-6
    assert abs(t[0][1] - 1.0) < 1e-6


def test_karaoke_events_and_ass_tags():
    audio = np.concatenate([silence(0.1), tone(1.0), silence(0.3), tone(1.0), silence(0.1)])
    timing = {"duration": 2.5, "sentences": [{"text": "あいう、えお。", "start": 0.0, "end": 2.5}]}
    events = build_events(timing, "", max_chars=4, linger=0.3, sub_y=800, hook_seconds=0,
                          hook_max_chars=8, hook_y=700, voice=(audio, SR))
    assert [e.lines[0] for e in events] == ["あいう、", "えお"]
    assert events[0].syllables[0][0] == "あ"
    # 2行目は読み始める少し前に出る
    assert abs(events[1].start - (events[1].syllables[0][1] - 0.1)) < 0.02
    ass = to_ass(events, width=1080, height=1920, font_name="X", font_size=100,
                 hook_font_size=100, outline=6, karaoke_colour="&H00FAC85A")
    assert r"\kf" in ass and "Style: Sub,X,100,&H00FAC85A,&H00FFFFFF" in ass
