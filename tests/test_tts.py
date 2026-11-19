import io

import numpy as np
import pytest
import soundfile as sf

from ai_shorts.errors import StoryTooLongError
from ai_shorts.tts import (
    VoiceSettings,
    build_segments,
    speed_candidates,
    synthesize_story,
)

SR = 48000
SETTINGS = VoiceSettings(
    speaker_id=1, sample_rate=SR, pause_sentence=0.5, pause_paragraph=0.8,
    pre_silence=1.0, post_silence=1.0,
)


class FakeClient:
    """1文字 0.2 秒 ÷ 話速 の音を返す。"""

    def __init__(self):
        self.synth_calls = 0

    def audio_query(self, text, speaker):
        return {"chars": len(text)}

    def synthesis(self, query, speaker):
        self.synth_calls += 1
        n = int(query["chars"] * 0.2 / query["speedScale"] * query["outputSamplingRate"])
        buf = io.BytesIO()
        sf.write(buf, np.full(n, 0.1, dtype=np.float32), query["outputSamplingRate"], format="WAV")
        return buf.getvalue()


def test_speed_candidates_ends_at_max():
    assert speed_candidates(0.92, 1.05) == [0.92, 0.95, 0.98, 1.01, 1.04, 1.05]
    assert speed_candidates(1.0, 1.0) == [1.0]


def test_timing_includes_silences_and_paragraph_pause():
    segs = build_segments(["あいう。えお。", "かき。"])  # 4, 3, 3 文字（句点込み）
    audio, speed, sentences, paragraphs = synthesize_story(
        FakeClient(), segs, SETTINGS, [1.0], max_seconds=60, log=lambda m: None
    )
    assert speed == 1.0
    starts = [(s["start"], s["end"]) for s in sentences]
    # 前 1.0 → 0.8 秒 → 文間 0.5 → 0.6 秒 → 段落間 0.8 → 0.6 秒 → 後 1.0
    assert starts == [(1.0, 1.8), (2.3, 2.9), (3.7, 4.3)]
    assert paragraphs == [
        {"index": 0, "start": 1.0, "end": 2.9},
        {"index": 1, "start": 3.7, "end": 4.3},
    ]
    assert len(audio) / SR == pytest.approx(5.3, abs=1e-3)


def test_speeds_up_until_it_fits():
    segs = build_segments(["あ" * 49 + "。"])  # 50 字 → 速度 1.0 で 10 秒 + 無音 2 秒
    _, speed, _, _ = synthesize_story(
        FakeClient(), segs, SETTINGS, [0.8, 0.9, 1.0], max_seconds=12.5, log=lambda m: None
    )
    assert speed == 1.0


def test_too_long_raises():
    segs = build_segments(["あ" * 99 + "。"])
    with pytest.raises(StoryTooLongError):
        synthesize_story(
            FakeClient(), segs, SETTINGS, [0.92, 1.05], max_seconds=10, log=lambda m: None
        )


def test_tts_text_removes_quotes_and_joins_adjacent_ones():
    from ai_shorts.tts import tts_text
    assert tts_text("僕は「勇気」を押した。") == "僕は勇気を押した。"
    assert tts_text("「勇気」「眠り」「やり直し」と書かれていた。") == "勇気、眠り、やり直しと書かれていた。"
    assert tts_text("『本』を読む") == "本を読む"


def test_queries_use_tts_text_not_display_text():
    seen = []

    class Recorder(FakeClient):
        def audio_query(self, text, speaker):
            seen.append(text)
            return super().audio_query(text, speaker)

    segs = build_segments(["僕は「勇気」を押した。"])
    synthesize_story(Recorder(), segs, SETTINGS, [1.0], max_seconds=60, log=lambda m: None)
    assert seen == ["僕は勇気を押した。"]
    assert segs[0].text == "僕は「勇気」を押した。"
