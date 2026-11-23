from ai_shorts import ruby
from ai_shorts.qa import check_subs, text_width
from ai_shorts.subs import build_learner_events, word_wrap
from ai_shorts.tts import tts_text


def test_parse_implicit_and_explicit():
    plain, spans = ruby.parse("地獄《じごく》の底《そこ》に｜極楽池《ごくらくいけ》がある。")
    assert plain == "地獄の底に極楽池がある。"
    assert [(s.start, s.end, s.reading) for s in spans] == [
        (0, 2, "じごく"), (3, 4, "そこ"), (5, 8, "ごくらくいけ")]


def test_strip_and_reading():
    text = "大泥棒《おおどろぼう》がいた。"
    assert ruby.strip(text) == "大泥棒がいた。"
    assert ruby.reading(text) == "おおどろぼうがいた。"
    assert tts_text("「蜘蛛《くも》の糸《いと》だ」") == "蜘蛛の糸だ"


def test_uncovered_kanji():
    assert ruby.uncovered_kanji("地獄《じごく》の底にいた。") == ["底"]
    assert ruby.uncovered_kanji("カンダタは、のぼった。") == []


def test_missing_readings_tolerates_long_vowel_spelling():
    # エンジンは「おう」を「おお」と書くことがある
    assert ruby.missing_readings("大泥棒《おおどろぼう》がいた。", "おおどろぼおが/いた") == []
    assert ruby.missing_readings("西洋《せいよう》の店《みせ》", "セーヨーノ/ミセ") == []
    assert ruby.missing_readings("大泥棒《おおどろぼう》がいた。", "だいどろぼおが/いた") == ["大泥棒《おおどろぼう》"]
    # 前の語の終わり（て）と次の語の頭（い）を、長音としてそろえない
    assert ruby.missing_readings("そして、一本《いっぽん》の糸《いと》", "そして/、/いっぽんの/いとお") == []


def test_word_wrap():
    assert word_wrap("A thread came down from heaven", 16) == ["A thread came", "down from heaven"]
    # 行数は変えずに長さをそろえる（最後に1語だけ残さない）
    assert word_wrap("He spared a little spider instead of stepping on it.", 25) == [
        "He spared a little", "spider instead of", "stepping on it."]


def _timing():
    return {"duration": 6.0, "sentences": [
        {"text": "地獄《じごく》の底《そこ》。", "start": 2.0, "end": 3.0},
        {"text": "糸《いと》が来《き》た。", "start": 3.5, "end": 5.0},
    ]}


def test_learner_events_place_ruby_over_kanji():
    events = build_learner_events(
        _timing(), ["The bottom of hell.", "A thread came."], "Learn Japanese",
        width=1080, font_size=80, ruby_size=36, en_size=44, max_chars=12, en_max_chars=30,
        sub_y=700, hook_seconds=2.0, hook_max_chars=20, hook_y=760,
    )
    hook = [e for e in events if e.style == "Hook"]
    assert hook and hook[0].end == 2.0
    first = [e for e in events if e.start == 2.0]
    sub = next(e for e in first if e.style == "Sub")
    assert sub.lines == ["地獄の底"]                 # 文末の「。」は出さない
    rubies = [e for e in first if e.style == "Ruby"]
    # 「地獄の底」は4字・中央寄せなので左端は 540 - 160 = 380。地獄は 0〜2 字目、底は 3 字目
    assert [(e.lines[0], e.x) for e in rubies] == [("じごく", 460), ("そこ", 660)]
    assert all(e.y < sub.y for e in rubies)
    en = next(e for e in first if e.style == "En")
    assert en.lines == ["The bottom of hell."] and en.y > sub.y
    assert sub.end == 3.5                            # 次の文が始まるまで残す


def test_em_ratio_of_subtitle_font():
    from pathlib import Path
    from ai_shorts.subs import em_ratio
    font = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "NotoSerifJP-Medium.otf"
    assert abs(em_ratio(font) - 1000 / 1437) < 0.001
    assert em_ratio(Path("no-such-font.otf")) == 1.0


def test_ruby_x_uses_em_ratio():
    events = build_learner_events(
        _timing(), ["The bottom of hell.", "A thread came."], "",
        width=1080, font_size=80, ruby_size=36, en_size=44, max_chars=12, en_max_chars=30,
        sub_y=700, hook_seconds=2.0, hook_max_chars=20, hook_y=760, em=0.5,
    )
    # 1字 40px。「地獄の底」は左端 540 - 80 = 460。地獄の中心は 460 + 40、底は 460 + 140
    rubies = [(e.lines[0], e.x) for e in events if e.style == "Ruby" and e.start == 2.0]
    assert rubies == [("じごく", 500), ("そこ", 600)]


def test_learner_events_need_one_translation_per_sentence():
    import pytest
    from ai_shorts.errors import AiShortsError
    with pytest.raises(AiShortsError):
        build_learner_events(
            _timing(), ["only one"], "", width=1080, font_size=80, ruby_size=36, en_size=44,
            max_chars=12, en_max_chars=30, sub_y=700, hook_seconds=2.0, hook_max_chars=20, hook_y=760,
        )


def test_check_subs_measures_english_narrower():
    assert text_width("abc", 40) == 72
    assert text_width("地獄", 40) == 80
    subs = {"width": 1080, "height": 1920, "font_size": {"Sub": 80, "En": 44, "Ruby": 36, "Hook": 80},
            "events": [
                {"style": "En", "lines": ["A" * 34], "y": 900},
                {"style": "Ruby", "lines": ["じごく"], "y": 650, "x": 460},
            ]}
    check = check_subs(subs, max_chars=12, hook_max_chars=20, margin=40, bottom_ratio=0.2, en_max_chars=34)
    assert check.passed, check.detail
