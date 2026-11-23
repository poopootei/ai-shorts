import numpy as np

from ai_shorts.subs import Layout, LessonLook, build_lesson_events, to_ass
from ai_shorts.tts import assemble_lesson, lesson_steps

CFG = {"normal_speed": 1.0, "slow_speed": 0.8, "sentence_hold": 1.0, "chunk_hold": 2.0,
       "shadow_ratio": 1.5, "next_seconds": 3.0}
SENTENCE = "小《ちい》さな蜘蛛《くも》を、踏《ふ》まずに助《たす》けたのです。"
BREAKDOWN = [
    {"ja": "小《ちい》さな蜘蛛《くも》を", "en": "a little spider"},
    {"ja": "踏《ふ》まずに", "en": "without stepping on", "note": "〜ずに = without ~ing"},
]


def _timing():
    steps = lesson_steps(SENTENCE, BREAKDOWN, CFG)
    sr = 100
    clips = [np.ones(sr * 2, dtype=np.float32) for _ in steps]   # どの読み上げも 2 秒
    audio, entries, paragraphs, lesson = assemble_lesson(
        steps, clips, sr, pre_silence=1.0, shadow_ratio=CFG["shadow_ratio"],
        next_seconds=CFG["next_seconds"])
    return audio, entries, paragraphs, lesson


def test_lesson_steps_order_and_speed():
    steps = lesson_steps(SENTENCE, BREAKDOWN, CFG)
    assert [s.role for s in steps] == ["sentence", "chunk", "chunk", "repeat"]
    assert [s.speed for s in steps] == [1.0, 0.8, 0.8, 0.8]
    assert [s.index for s in steps if s.role == "chunk"] == [0, 1]


def test_assemble_lesson_timeline():
    audio, entries, paragraphs, lesson = _timing()
    # 1.0 前の無音 / 文 1.0〜3.0 +1.0 / かたまり 4.0〜6.0 +2.0、8.0〜10.0 +2.0 / ゆっくり 12.0〜14.0
    assert [(e["role"], e["start"], e["end"]) for e in entries] == [
        ("sentence", 1.0, 3.0), ("chunk", 4.0, 6.0), ("chunk", 8.0, 10.0), ("repeat", 12.0, 14.0)]
    assert lesson["shadow"] == [14.0, 17.0]          # まねる間 = 2.0 × 1.5
    assert lesson["next"] == [17.0, 20.0]
    assert len(audio) == 2000
    assert [(p["index"], p["start"], p["end"]) for p in paragraphs] == [
        (0, 1.0, 3.0), (1, 4.0, 10.0), (2, 12.0, 20.0)]


def test_lesson_screens():
    audio, entries, paragraphs, lesson = _timing()
    timing = {"duration": 20.0, "sentences": entries, "lesson": lesson}
    lo = Layout(1080, 76, 34, 46, 12, 34, em=0.7)
    look = LessonLook(label_size=44, note_size=46, note_max_chars=30,
                      chunk=Layout(1080, 120, 50, 54, 9, 30, em=0.7))
    events = build_lesson_events(
        timing, "Why 踏まずに?", "He saved a little spider instead of stepping on it.",
        BREAKDOWN, "Next: The Buddha remembers.", lo=lo, look=look, sub_y=700, label_y=380,
        hook_y=760, hook_max_chars=22)
    labels = [(e.lines[0], e.start, e.end) for e in events if e.style == "Label"]
    assert labels == [("Today's line", 1.0, 4.0), ("Breakdown 1/2", 4.0, 8.0),
                      ("Breakdown 2/2", 8.0, 12.0), ("Repeat after me", 12.0, 14.0),
                      ("Your turn!", 14.0, 17.0), ("Next line", 17.0, 20.0)]
    hook = [e for e in events if e.style == "Hook"]
    assert hook and hook[0].end == 1.0
    note = [e for e in events if e.style == "Note"]
    assert note and note[0].lines == ["〜ずに = without ~ing"] and note[0].start == 8.0
    en_at_chunk2 = next(e for e in events if e.style == "En" and e.start == 8.0)
    assert note[0].y > en_at_chunk2.y                 # メモは意味の下
    # まねる画面は、ゆっくり読む間からまねる間の終わりまで文を残す
    assert any(e.style == "Sub" and e.start == 12.0 and e.end == 17.0 for e in events)
    # 分解のかたまりは大きく出す
    assert any(e.style == "Sub" and e.start == 4.0 and e.size == 120 for e in events)
    # 画面ごとに板を1枚、見出しと文字を囲むように敷く
    panels = [e for e in events if e.style == "Panel"]
    assert [(p.start, p.end) for p in panels] == [(1.0, 4.0), (4.0, 8.0), (8.0, 12.0), (12.0, 17.0), (17.0, 20.0)]
    first_label = next(e for e in events if e.style == "Label")
    assert panels[0].y < first_label.y - 44 / 2
    ass = to_ass(events, width=1080, height=1920, font_name="F", font_size=76, hook_font_size=80,
                 outline=6, ruby_size=34, en_size=46, label_size=44, lesson=True)
    assert r"{\an7\pos(40," in ass and r"\p1}m 0 0 l 1000 0" in ass
    assert "Dialogue: 0,0:00:01.00,0:00:04.00,Panel" in ass
    assert "Dialogue: 1,0:00:04.00,0:00:08.00,Sub" in ass and r"\fs120" in ass


def test_fit_ja_breaks_only_at_natural_points():
    from ai_shorts.subs import fit_ja, wrap
    plain = "小さな蜘蛛を、踏まずに助けたのです"
    size, max_chars = fit_ja(plain, avail=920, em=0.69, cap=150, floor=100, max_lines=2)
    lines = wrap(plain, max_chars)
    assert lines == ["小さな蜘蛛を、", "踏まずに助けたのです"]
    assert 10 * size * 0.69 <= 920 and size >= 120
    # 1行に収める（かたまり）。上限まで大きくなる
    assert fit_ja("踏まずに", avail=920, em=0.69, cap=180, floor=120, max_lines=1)[0] == 180


def test_fit_en_keeps_words_whole_and_balanced():
    from ai_shorts.subs import fit_en, text_units
    size, lines = fit_en("He spared a little spider instead of stepping on it.",
                         avail=920, em=0.69, cap=80, floor=56, max_lines=3)
    assert size == 80 and len(lines) <= 3
    assert all(text_units(line) * size * 0.69 <= 920 for line in lines)
    assert " ".join(lines) == "He spared a little spider instead of stepping on it."


def test_unit_wrap_keeps_parentheses_together():
    from ai_shorts.subs import unit_wrap
    lines = unit_wrap('〜のです explains: "(you see,) he saved it."', 22)
    assert not any(line.endswith("(you") for line in lines)
    assert any('"(you see,)' in line for line in lines)
