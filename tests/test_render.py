import numpy as np
import pyloudnorm as pyln
import pytest

from ai_shorts.render import (
    image_boundaries,
    mix,
    normalize_loudness,
    segment_durations,
    soft_limit,
    video_filter,
)

SR = 48000


def tone(seconds, amp=0.1, freq=220.0):
    t = np.arange(int(seconds * SR)) / SR
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_mix_pads_short_bgm_and_applies_gain():
    voice = np.zeros(SR, dtype=np.float32)
    bgm = np.ones((SR // 2, 2), dtype=np.float32)
    out = mix(voice, bgm, bgm_gain_db=-20)
    assert out.shape == (SR, 2)
    assert out[0, 0] == pytest.approx(0.1)
    assert out[-1, 0] == 0.0


def test_mix_without_bgm_is_stereo_voice():
    out = mix(tone(1), None, -18)
    assert out.shape == (SR, 2)


def test_normalize_hits_target():
    x = np.repeat(tone(5)[:, None], 2, axis=1)
    y = normalize_loudness(x, SR, -14)
    assert pyln.Meter(SR).integrated_loudness(y) == pytest.approx(-14, abs=0.1)


def test_soft_limit_keeps_below_ceiling_and_leaves_quiet_parts():
    x = np.array([0.1, -0.5, 0.9, -1.5, 3.0], dtype=np.float32)
    y = soft_limit(x, knee=0.85, ceiling=0.98)
    assert np.all(np.abs(y) <= 0.98)
    assert y[0] == x[0] and y[1] == x[1]
    assert np.all(np.sign(y) == np.sign(x))


def test_video_filter_zoom_only_with_image():
    common = dict(width=1080, height=1920, durations=[30.0], crossfade=0.5, zoom_end=1.08,
                  subs=None, credit=None)
    with_img = video_filter(has_images=True, **common)
    without = video_filter(has_images=False, **common)
    assert "eval=frame" in with_img
    assert "eval=frame" not in without
    assert with_img.endswith("format=yuv420p[v]")


def test_segment_durations_sum_to_total_after_crossfades():
    d = segment_durations([10.0, 20.0], 30.0, 0.5)
    assert d == [10.25, 10.5, 10.25]
    assert sum(d) - 2 * 0.5 == pytest.approx(30.0)
    assert segment_durations([], 30.0, 0.5) == [30.0]


def test_xfade_offsets_center_on_boundaries():
    vf = video_filter(width=1080, height=1920, durations=[10.25, 10.5, 10.25], crossfade=0.5,
                      zoom_end=1.08, has_images=True, subs="subtitles=filename=x.ass", credit=None)
    assert "offset=9.750[x1]" in vf     # 境目 10.0 の前後 0.25 秒
    assert "offset=19.750[x2]" in vf    # 境目 20.0 の前後 0.25 秒
    assert vf.endswith("[x2]subtitles=filename=x.ass,format=yuv420p[v]")


def test_image_boundaries_use_paragraph_gaps():
    timing = {"paragraphs": [{"start": 1.0, "end": 10.0}, {"start": 10.8, "end": 20.0},
                             {"start": 20.8, "end": 30.0}]}
    assert image_boundaries(timing, 3, 31.0) == [10.4, 20.4]


def test_rel_to_root_reaches_shared_assets_from_channel(tmp_path):
    from ai_shorts.config import Project
    from ai_shorts.render import rel_to_root
    root = tmp_path / "channels" / "aozora"
    project = Project(root=root, config={})
    assert rel_to_root(project, root / "work" / "x" / "subs.ass") == "work/x/subs.ass"
    assert rel_to_root(project, tmp_path / "assets" / "fonts") == "../../assets/fonts"
