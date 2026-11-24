from ai_shorts.qa import check_subs
from ai_shorts.subs import atoms, build_events, display_text, to_ass, wrap


def test_display_text_drops_final_period_only():
    assert display_text("扉が開いた。") == "扉が開いた"
    assert display_text("「嫌だ。」") == "「嫌だ。」"


def test_atoms_break_after_punctuation_and_hiragana_to_kanji():
    assert atoms("駅の裏の路地に、誰も", 15) == ["駅の", "裏の", "路地に、", "誰も"]


def test_atoms_do_not_start_line_with_small_kana_or_long_vowel():
    assert "".join(atoms("コーヒーだった", 15)) == "コーヒーだった"
    assert all(not a.startswith(("ー", "っ")) for a in atoms("まっすぐコーヒー", 15))


def test_atoms_hard_split_long_run():
    # 2字だけ次の行に回さない（「タチ」→「ソタチ」）
    assert atoms("アイウエオカキクケコサシスセソタチ", 15) == ["アイウエオカキクケコサシスセ", "ソタチ"]


def test_atoms_do_not_break_after_small_tsu():
    assert "引っ越して" in "|".join(atoms("うちのとなりに引っ越してきまして", 10)).split("|")[1]


def test_atoms_keep_honorific_prefix_with_next_word():
    assert atoms("迷子のお知らせ", 10) == ["迷子の", "お知らせ"]
    assert atoms("一階でお待ちです", 10) == ["一階で", "お待ちです"]
    assert atoms("「お世話になりました。", 10) == ["「お世話に", "なりました。"]


def test_atoms_keep_okurigana_compounds():
    assert atoms("「この星の生き物を調べる」", 10) == ["「この", "星の", "生き物を", "調べる」"]
    assert atoms("落とし物を拾った", 10) == ["落とし物を", "拾った"]
    assert atoms("犬が物を運ぶ", 10) == ["犬が", "物を", "運ぶ"]


def test_atoms_keep_compound_verbs_and_nouns():
    assert atoms("きのうの売れ残りです", 10) == ["きのうの", "売れ残りです"]
    assert atoms("空を見上げた", 10) == ["空を", "見上げた"]


def test_atoms_split_long_hiragana_after_adverbial_ku():
    assert atoms("あまりおいしくありません」", 10) == ["あまりおいしく", "ありません」"]


def test_wrap_does_not_carry_on_past_period_then_break_mid_phrase():
    lines = wrap("「天気は、西からやってくるでしょう。娘の町の今日が、この町の明日なんです」", 10)
    assert "くるでしょう。" in lines
    assert "娘の町の今日が、" in lines


def test_atoms_split_long_hiragana_after_particle():
    assert atoms("西からやってくるでしょう。", 10) == ["西からやって", "くるでしょう。"]


def test_atoms_split_long_at_kanji_to_hiragana_without_particle():
    assert atoms("最後尾だったんですか」", 10) == ["最後尾", "だったんですか」"]


def test_atoms_particle_split_does_not_leave_tiny_tail():
    assert atoms("半年先までうまっている", 10) == ["半年先まで", "うまっている"]


def test_atoms_split_long_hiragana_after_n_before_hard_split():
    # 助詞がないときは「ん」の後で切る（みなさんそうな｜ります」にしない）
    assert atoms("みなさんそうなります」", 10) == ["みなさん", "そうなります」"]


def test_atoms_hard_split_does_not_leave_tiny_tail():
    assert atoms("アイウエオカキクケコサ」", 10) == ["アイウエオカキク", "ケコサ」"]


def test_wrap_does_not_end_line_with_determiner():
    lines = wrap("娘の町の今日が、この町の明日なんです」", 10)
    assert all(not line.endswith("この") for line in lines)
    assert all(len(line) <= 10 for line in lines)


def test_wrap_does_not_start_line_with_lone_kanji():
    assert wrap("しらがまじりの男の子。お母さまが、", 10) == ["しらがまじりの", "男の子。お母さまが、"]


def test_wrap_respects_limit_and_prefers_punctuation():
    lines = wrap("それでも一口飲むと、ずっと言えなかった退職届を出す気になれた", 15)
    assert all(len(line) <= 15 for line in lines)
    assert lines[0] == "それでも一口飲むと、"
    assert "".join(lines) == "それでも一口飲むと、ずっと言えなかった退職届を出す気になれた"


def test_wrap_prefers_punctuation_over_mid_phrase_break():
    assert wrap("子どものころ、誕生日ごとに背を測り、鉛筆で線を引いた柱だ", 15) == [
        "子どものころ、", "誕生日ごとに背を測り、", "鉛筆で線を引いた柱だ"]


def test_wrap_keeps_quote_together():
    assert wrap("男は湯のみを差し出し、「少し休んでいきなさい」と笑った", 15) == [
        "男は湯のみを差し出し、", "「少し休んでいきなさい」", "と笑った"]


def test_wrap_does_not_start_line_with_particle_after_quote():
    assert wrap("僕は百円を入れて「勇気」を押した", 15) == ["僕は百円を入れて", "「勇気」を押した"]


def test_wrap_balances_ties():
    assert wrap("扉が開くと、畳の小部屋に白髪の男が座っていた", 15) == [
        "扉が開くと、畳の小部屋に", "白髪の男が座っていた"]


def test_wrap_short_text_is_one_line():
    assert wrap("中には誰もいない", 15) == ["中には誰もいない"]


TIMING = {
    "duration": 8.0,
    "sentences": [
        {"text": "駅の裏の路地に、誰も補充しない自動販売機がある。", "start": 1.0, "end": 5.0},
        {"text": "中には誰もいない。", "start": 5.5, "end": 7.0},
    ],
}


def events():
    return build_events(TIMING, "その自販機は、願いを売っていた", max_chars=15, linger=0.3,
                        sub_y=864, hook_seconds=2.0, hook_max_chars=10, hook_y=538)


def test_build_events_splits_time_by_characters_and_lingers():
    ev = events()
    assert ev[0].style == "Hook" and ev[0].lines == ["その自販機は、", "願いを売っていた"]
    subs = [e for e in ev if e.style == "Sub"]
    assert [e.lines[0] for e in subs] == ["駅の裏の路地に、", "誰も補充しない自動販売機がある", "中には誰もいない"]
    # 8字 + 15字 で 4 秒を分ける。文末は次の文まで最大 0.3 秒残す
    assert subs[0].start == 1.0 and subs[0].end == round(1.0 + 4 * 8 / 23, 3)
    assert subs[1].end == 5.3
    assert subs[2].end == 7.3


def test_hook_alone_ends_before_first_sentence():
    ev = build_events(TIMING, "その自販機は", max_chars=15, linger=0.3, sub_y=864,
                      hook_seconds=2.0, hook_max_chars=10, hook_y=760, hook_alone=True)
    hook = ev[0]
    first_sub = next(e for e in ev if e.style == "Sub")
    assert hook.style == "Hook" and hook.end == 1.0 <= first_sub.start


def test_hook_box_style():
    ass = to_ass(events(), width=1080, height=1920, font_name="F", font_size=64, hook_font_size=104,
                 outline=4, hook_box=True, hook_box_opacity=0.75, hook_box_padding=36)
    # BorderStyle 3（箱）、箱の色は 25% 透明の黒、余白 36
    assert "Style: Hook,F,104,&H00FFFFFF,&H000000FF,&H40000000,&H64000000,0,0,0,0,100,100,0,0,3,36," in ass
    assert "Style: Sub,F,64,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,4," in ass


def test_to_ass_has_styles_and_positions():
    ass = to_ass(events(), width=1080, height=1920, font_name="Noto Serif JP Medium",
                 font_size=64, hook_font_size=88, outline=4)
    assert "PlayResY: 1920" in ass
    assert "Style: Sub,Noto Serif JP Medium,64" in ass
    assert r"{\an5\pos(540,538)\fad(0,250)}その自販機は、\N願いを売っていた" in ass
    assert "Dialogue: 0,0:00:01.00," in ass


def _subs_json(lines, y=864):
    return {"width": 1080, "height": 1920, "font_size": {"Sub": 64, "Hook": 88},
            "events": [{"start": 0, "end": 1, "style": "Sub", "lines": lines, "y": y}]}


def test_check_subs_passes_and_flags_problems():
    ok = check_subs(_subs_json(["中には誰もいない"]), max_chars=15, hook_max_chars=10,
                    margin=40, bottom_ratio=0.2)
    assert ok.passed
    too_long = check_subs(_subs_json(["あ" * 16]), max_chars=15, hook_max_chars=10,
                          margin=40, bottom_ratio=0.2)
    assert not too_long.passed
    too_low = check_subs(_subs_json(["中には"], y=1700), max_chars=15, hook_max_chars=10,
                         margin=40, bottom_ratio=0.2)
    assert not too_low.passed
