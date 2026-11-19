from ai_shorts.story import split_paragraphs, split_sentences


def test_split_sentences_basic():
    assert split_sentences("僕は押した。缶が出た！本当？") == ["僕は押した。", "缶が出た！", "本当？"]


def test_split_sentences_keeps_quotes_together():
    text = "彼は「やめて！ もう嫌だ。」と言った。そして帰った。"
    assert split_sentences(text) == ["彼は「やめて！ もう嫌だ。」と言った。", "そして帰った。"]


def test_split_sentences_repeated_marks_and_tail():
    assert split_sentences("えっ！？まさか") == ["えっ！？", "まさか"]


def test_split_paragraphs_skips_blank_lines():
    assert split_paragraphs("一段落目。\n\n  二段落目。 \n") == ["一段落目。", "二段落目。"]
