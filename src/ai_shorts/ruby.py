"""ルビ（ふりがな）: 青空文庫と同じ書き方で、物語の本文に読みを書く。

    地獄《じごく》の底《そこ》        漢字が続くところ全体に読みが付く
    ｜極楽池《ごくらくいけ》          ｜ から 《 までに付ける（区切りを明示するとき）

読み上げ（tts）と字数の数え方はルビを外した文（plain）を使う。
学習者向けの字幕（subs.mode: learner）は、ルビを漢字の上に小さく出す。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_KANJI_CHARS = "㐀-䶿一-鿿豈-﫿々〆ヵヶ"
_RUBY = re.compile(rf"(?:｜([^｜《》]+)|([{_KANJI_CHARS}]+))《([^《》]+)》")
_KANJI = re.compile(rf"[{_KANJI_CHARS}]")


@dataclass(frozen=True)
class Span:
    start: int     # plain の中の位置
    end: int
    reading: str


def parse(text: str) -> tuple[str, list[Span]]:
    """ルビ付きの文 → （ルビを外した文, ルビの位置と読み）"""
    plain: list[str] = []
    spans: list[Span] = []
    pos = length = 0
    for m in _RUBY.finditer(text):
        before = text[pos:m.start()]
        plain.append(before)
        length += len(before)
        base = m.group(1) or m.group(2)
        spans.append(Span(length, length + len(base), m.group(3)))
        plain.append(base)
        length += len(base)
        pos = m.end()
    plain.append(text[pos:])
    return "".join(plain).replace("｜", ""), spans


def strip(text: str) -> str:
    return parse(text)[0]


def reading(text: str) -> str:
    """ルビの付いた漢字を読みに置き換えた文（読み上げの読みと比べるのに使う）。"""
    plain, spans = parse(text)
    out, pos = [], 0
    for s in spans:
        out.append(plain[pos:s.start])
        out.append(s.reading)
        pos = s.end
    out.append(plain[pos:])
    return "".join(out)


def uncovered_kanji(text: str) -> list[str]:
    """ルビの付いていない漢字（学習者向けでは、すべての漢字に読みを付ける）。"""
    plain, spans = parse(text)
    covered = {i for s in spans for i in range(s.start, s.end)}
    return [c for i, c in enumerate(plain) if _KANJI.match(c) and i not in covered]


# ---- 読みの比べ方 ----------------------------------------------------------
# エンジンの読みは「だいどろぼお」「せえよお」のように長音を母音で書くことがある。
# 両方を同じ形にそろえてから比べる（おう→おお、えい→ええ、ー→前の母音）。

_VOWEL_ROWS = {
    "a": "あかさたなはまやらわがざだばぱぁゃゎ",
    "i": "いきしちにひみりぎじぢびぴぃ",
    "u": "うくすつぬふむゆるぐずづぶぷぅゅっ",
    "e": "えけせてねへめれげぜでべぺぇ",
    "o": "おこそとのほもよろをごぞどぼぽぉょ",
}
_VOWEL_OF = {c: v for v, chars in _VOWEL_ROWS.items() for c in chars}
_VOWEL_KANA = {"a": "あ", "i": "い", "u": "う", "e": "え", "o": "お"}


def to_hiragana(text: str) -> str:
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in text)


def normalize_kana(text: str) -> str:
    """ひらがなにそろえ、かな以外を消し、長音の書き方をそろえる。"""
    kana = [c for c in to_hiragana(text) if "ぁ" <= c <= "ゖ" or c == "ー"]
    out: list[str] = []
    for c in kana:
        prev = _VOWEL_OF.get(out[-1]) if out else None
        if c == "ー" and prev:
            c = _VOWEL_KANA[prev]
        elif c == "う" and prev == "o":
            c = "お"
        elif c == "い" and prev == "e":
            c = "え"
        out.append(c)
    return "".join(out)


def _kana_only(text: str) -> str:
    return "".join(c for c in to_hiragana(text) if "ぁ" <= c <= "ゖ" or c == "ー")


def missing_readings(text: str, engine_reading: str) -> list[str]:
    """ルビの読みのうち、エンジンの読みに出てこないもの（読み間違いの候補）。

    長音をそろえた形と、そろえない形の両方で探す（語の切れ目をまたいで「て｜い」が「てえ」に
    なるような、そろえ過ぎを避けるため）。"""
    got_norm, got_raw = normalize_kana(engine_reading), _kana_only(engine_reading)
    plain, spans = parse(text)
    return [f"{plain[s.start:s.end]}《{s.reading}》" for s in spans
            if normalize_kana(s.reading) not in got_norm and _kana_only(s.reading) not in got_raw]
