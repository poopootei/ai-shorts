"""字幕（subs）: work/{id}/timing.json → work/{id}/subs.ass, subs.json

文を1行 max_chars_per_line 字以内に区切り、文の時間を字数に比例して割り振る。
区切る位置は、句読点の後と「ひらがな → 漢字・カタカナ」の切れ目（文節の切れ目に近い）から選び、
行の長さがそろうようにする。冒頭 hook_seconds 秒は hook を大きく出す。
hook_alone なら hook は最初の文が始まるまでに消し、本文の字幕と重ねない（D-013）。
hook_box なら hook を半透明の帯で囲み、本文と見た目でも区別する。
subs.json は qa が行の長さと位置を検査するのに使う。
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

from . import ruby
from .config import Project
from .errors import AiShortsError
from .story import load_approved

BREAK_AFTER = "、。，．！？!?」』）)…"
NO_LINE_START = BREAK_AFTER + "ーぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮ・"
OPEN_QUOTES, CLOSE_QUOTES = "「『", "」』"
# 行の区切り方のコスト。行の余り字数 s に対して s + s²/max_chars（行が少なく、長さがそろうほど安い）に、次の罰を足す。
# 句読点以外で切ると、1行増やすより高くつくようにしてある（「背を｜測り」より「、」で切る）。
NOT_AT_PUNCT_PENALTY = 30
INSIDE_QUOTE_PENALTY = 25     # かぎかっこの途中で切る（「少し｜休んで」）
PARTICLE_START_PENALTY = 28   # 」のすぐ後の助詞で行が始まる（「勇気」｜を押した）


@dataclass
class Event:
    start: float
    end: float
    style: str
    lines: list[str]
    y: int
    x: int | None = None   # None なら画面の中央（ルビは漢字の真上に置く）
    size: int | None = None  # None ならスタイルの大きさ（分解のかたまりだけ大きくする、など）
    layer: int = 0           # レッスン形式では、板（Panel）を 0、文字を 1 にして板の上に描く


def _is_hiragana(c: str) -> bool:
    return "ぁ" <= c <= "ゟ"


def display_text(sentence: str) -> str:
    """字幕では文末の「。」を出さない（「。」」のようにかっこの中は残す）。ルビは外す。"""
    return ruby.strip(sentence).rstrip("。")


def atoms(text: str, max_chars: int) -> list[str]:
    """改行してよい位置で区切った最小単位。max_chars を超えるものはそこで切る。"""
    out: list[str] = []
    cur = ""
    for i, c in enumerate(text):
        cur += c
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if not nxt:
            break
        boundary = (c in BREAK_AFTER and nxt not in BREAK_AFTER) or (
            _is_hiragana(c) and not _is_hiragana(nxt) and nxt not in NO_LINE_START
        )
        if boundary:
            out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    result: list[str] = []
    for a in out:
        while len(a) > max_chars:
            result.append(a[:max_chars])
            a = a[max_chars:]
        result.append(a)
    return result


def wrap(text: str, max_chars: int) -> list[str]:
    """句読点の後で、かぎかっこの外で切ることを優先し、行数が少なくなるように区切る。"""
    parts = atoms(text, max_chars)
    n = len(parts)
    # depth[j]: parts[:j] のあとで開いたままのかぎかっこの数
    depth = [0] * (n + 1)
    for j, part in enumerate(parts, start=1):
        d = depth[j - 1]
        for c in part:
            d += (c in OPEN_QUOTES) - (c in CLOSE_QUOTES)
        depth[j] = max(0, d)

    def break_cost(j: int) -> int:
        if j == n:
            return 0
        last, nxt = parts[j - 1][-1], parts[j][0]
        cost = 0 if last in BREAK_AFTER else NOT_AT_PUNCT_PENALTY
        if depth[j] > 0:
            cost += INSIDE_QUOTE_PENALTY
        if last in CLOSE_QUOTES and _is_hiragana(nxt):
            cost += PARTICLE_START_PENALTY
        return cost

    best: list[tuple[float, int]] = [(0.0, -1)] + [(math.inf, -1)] * n
    for j in range(1, n + 1):
        length = 0
        for i in range(j - 1, -1, -1):
            length += len(parts[i])
            if length > max_chars:
                break
            slack = max_chars - length
            cost = best[i][0] + slack + slack * slack / max_chars + break_cost(j)
            if cost < best[j][0]:
                best[j] = (cost, i)
    lines: list[str] = []
    j = n
    while j > 0:
        i = best[j][1]
        lines.append("".join(parts[i:j]))
        j = i
    return lines[::-1]


def build_events(
    timing: dict, hook: str, *, max_chars: int, linger: float, sub_y: int,
    hook_seconds: float, hook_max_chars: int, hook_y: int, hook_alone: bool = False,
) -> list[Event]:
    events: list[Event] = []
    sentences = timing["sentences"]
    hook_end = hook_seconds
    if hook_alone and sentences:
        hook_end = min(hook_end, sentences[0]["start"])
    if hook and hook_end > 0:
        events.append(Event(0.0, round(hook_end, 3), "Hook", wrap(hook, hook_max_chars), hook_y))

    for k, s in enumerate(sentences):
        lines = wrap(display_text(s["text"]), max_chars)
        total = sum(len(line) for line in lines)
        t = s["start"]
        span = s["end"] - s["start"]
        next_start = sentences[k + 1]["start"] if k + 1 < len(sentences) else timing["duration"]
        for li, line in enumerate(lines):
            end = t + span * len(line) / total
            if li == len(lines) - 1:
                end = s["end"] + min(linger, max(0.0, next_start - s["end"]))
            events.append(Event(round(t, 3), round(end, 3), "Sub", [line], sub_y))
            t = end
    return events


def _greedy_wrap(words: list[str], max_chars: int) -> list[str]:
    lines: list[str] = []
    cur = ""
    for word in words:
        if cur and len(cur) + 1 + len(word) > max_chars:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    if cur:
        lines.append(cur)
    return lines


def text_units(s: str) -> float:
    """字幕の幅の単位。全角（日本語）= 1、半角（英語）≒ 0.6（qa.text_width と同じ見積もり）。"""
    return sum(1.0 if ord(c) >= 0x2E80 else 0.6 for c in s)


def unit_wrap(text: str, max_units: float) -> list[str]:
    """単語の切れ目で、幅（text_units）が max_units を超えないように折り返す。
    行数はそのままに、行の幅をできるだけそろえる。日本語が混ざったメモにも使える。
    かっこ（ ）の中では折り返さない（「(you / see,)」のようにならないように）。"""
    words: list[str] = []
    for token in text.split():
        if words and words[-1].count("(") > words[-1].count(")"):
            words[-1] += " " + token
        else:
            words.append(token)

    def greedy(limit: float) -> list[str]:
        lines, cur = [], ""
        for word in words:
            cand = f"{cur} {word}" if cur else word
            if cur and text_units(cand) > limit:
                lines.append(cur)
                cur = word
            else:
                cur = cand
        return lines + ([cur] if cur else [])

    lines = greedy(max_units)
    if len(lines) < 2:
        return lines
    target = text_units(text) / len(lines)
    step = 0.3
    limit = target
    while limit < max_units:
        balanced = greedy(limit)
        if len(balanced) == len(lines):
            return balanced
        limit += step
    return lines


def fit_ja(plain: str, *, avail: float, em: float, cap: int, floor: int,
           max_lines: int) -> tuple[int, int]:
    """日本語を、不自然な折り返しをせずに max_lines 行に収まる、いちばん大きい大きさ。

    折り返してよいのは、句読点の後と、ひらがな → 漢字・カタカナの切れ目（atoms の区切り）だけ。
    1つの区切りが1行に入らない大きさは使わない（語の途中で切ることになるため）。
    （大きさ, 1行の字数）を返す。どの大きさでも収まらなければ floor。"""
    pieces = atoms(plain, 10 ** 6)
    longest = max((len(p) for p in pieces), default=0)
    for size in range(cap, floor - 1, -2):
        max_chars = int(avail // (size * em))
        if max_chars >= longest and len(wrap(plain, max_chars)) <= max_lines:
            return size, max_chars
    return floor, int(avail // (floor * em))


def fit_en(text: str, *, avail: float, em: float, cap: int, floor: int,
           max_lines: int) -> tuple[int, list[str]]:
    """英文（メモ）を、単語の途中で切らずに max_lines 行に収まる、いちばん大きい大きさと行。"""
    for size in range(cap, floor - 1, -2):
        max_units = avail / (size * em)
        lines = unit_wrap(text, max_units)
        # 1語（かっこのまとまり）が1行に入らない大きさは使わない
        if len(lines) <= max_lines and all(text_units(line) <= max_units for line in lines):
            return size, lines
    return floor, unit_wrap(text, avail / (floor * em))


def word_wrap(text: str, max_chars: int) -> list[str]:
    """英文を単語の切れ目で折り返す。行数はそのままに、行の長さをできるだけそろえる
    （最後の行に1語だけ残る「…stepping on / it.」を避ける）。"""
    words = text.split()
    lines = _greedy_wrap(words, max_chars)
    if len(lines) < 2:
        return lines
    total = len(" ".join(words))
    for limit in range(-(-total // len(lines)), max_chars):
        balanced = _greedy_wrap(words, limit)
        if len(balanced) == len(lines):
            return balanced
    return lines


def em_ratio(font_path: Path) -> float:
    """ASS の文字の大きさに対する、全角1字の幅の比率。

    libass は「文字の大きさ = フォントの上端から下端まで（usWinAscent + usWinDescent）」として
    拡大するので、全角1字（1em）の幅は 大きさ × unitsPerEm / (ascent + descent) になる。
    Noto Serif JP は 1000 / (1151 + 286) ≒ 0.696。読めなければ 1.0（ルビが少しずれる）。
    """
    import struct
    try:
        data = font_path.read_bytes()
        tables = {}
        for i in range(struct.unpack(">H", data[4:6])[0]):
            tag, _, off, _ = struct.unpack(">4sIII", data[12 + 16 * i:28 + 16 * i])
            tables[tag] = off
        upem = struct.unpack(">H", data[tables[b"head"] + 18:tables[b"head"] + 20])[0]
        os2 = tables[b"OS/2"]
        win_ascent, win_descent = struct.unpack(">HH", data[os2 + 74:os2 + 78])
        return upem / (win_ascent + win_descent)
    except (OSError, KeyError, struct.error, ZeroDivisionError):
        return 1.0


@dataclass(frozen=True)
class Layout:
    """学習者向けの字幕の大きさ（config の subs.*）。"""
    width: int
    font_size: int
    ruby_size: int
    en_size: int
    max_chars: int
    en_max_chars: int
    em: float = 1.0      # 全角1字の幅 / 文字の大きさ（em_ratio）
    gap: float = 0.6     # 日本語と英訳の間（英訳の大きさに対する比）


def ruby_block(text: str, en: str, start: float, end: float, center_y: float,
               lo: Layout, en_lines: list[str] | None = None) -> tuple[list[Event], float]:
    """日本語（ルビ付き）と、その下の英訳をひとまとまりで出す。（イベント, 英訳の下端の y）を返す。

    日本語は全角なので1字の幅がそろう（= font_size × em）。それを使って、ルビを漢字の真上に置く。
    """
    events: list[Event] = []
    ruby_h = lo.ruby_size * 1.15
    line_h = lo.font_size * 1.2 + ruby_h
    plain, spans = ruby.parse(text)
    lines = wrap(plain.rstrip("。"), lo.max_chars)
    top = center_y - len(lines) * line_h / 2
    offset = 0
    char_w = lo.font_size * lo.em
    t0, t1 = round(start, 3), round(end, 3)
    for li, line in enumerate(lines):
        y = round(top + li * line_h + ruby_h + lo.font_size * 0.6)
        events.append(Event(t0, t1, "Sub", [line], y, size=lo.font_size))
        left = lo.width / 2 - len(line) * char_w / 2
        for sp in spans:
            if not offset <= sp.start < offset + len(line):
                continue
            s1 = min(sp.end, offset + len(line))
            x = round(left + ((sp.start - offset) + (s1 - offset)) / 2 * char_w)
            # 漢字の上端（中心から 0.5em）の少し上に、ルビの中心を置く
            ry = round(y - char_w * 0.5 - lo.ruby_size * lo.em * 0.5 - 6)
            events.append(Event(t0, t1, "Ruby", [sp.reading], ry, x, size=lo.ruby_size))
        offset += len(line)
    bottom = top + len(lines) * line_h
    if en:
        en_lines = en_lines or word_wrap(en, lo.en_max_chars)
        en_block = lo.en_size * 1.25 * len(en_lines)
        events.append(Event(t0, t1, "En", en_lines, round(bottom + lo.en_size * lo.gap + en_block / 2),
                            size=lo.en_size))
        bottom += lo.en_size * lo.gap + en_block
    return events, bottom


def build_learner_events(
    timing: dict, translations: list[str], hook: str, *, width: int, font_size: int,
    ruby_size: int, en_size: int, max_chars: int, en_max_chars: int, sub_y: int,
    hook_seconds: float, hook_max_chars: int, hook_y: int, gap: float = 0.6,
    em: float = 1.0,
) -> list[Event]:
    """学習者向け（物語形式）：文ごとに、日本語（ルビ付き）と英訳を同時に出す。次の文が始まるまで残す。
    hook は英語（単語で折り返す）。"""
    sentences = timing["sentences"]
    if len(translations) != len(sentences):
        raise AiShortsError(
            f"英訳が {len(translations)} 文、本文が {len(sentences)} 文で、数が合いません（translations を直してください）。"
        )
    lo = Layout(width, font_size, ruby_size, en_size, max_chars, en_max_chars, em, gap)
    events: list[Event] = []
    if hook and sentences:
        hook_end = min(hook_seconds, sentences[0]["start"])
        if hook_end > 0:
            events.append(Event(0.0, round(hook_end, 3), "Hook", word_wrap(hook, hook_max_chars), hook_y))
    for k, s in enumerate(sentences):
        end = sentences[k + 1]["start"] if k + 1 < len(sentences) else timing["duration"]
        events += ruby_block(s["text"], translations[k], s["start"], end, sub_y, lo)[0]
    return events


@dataclass(frozen=True)
class LessonLook:
    """レッスン形式の見た目（config の subs.* と lesson.*）。D-024"""
    label_size: int
    note_size: int
    note_max_chars: int
    chunk: Layout              # 分解のかたまりは大きく出す
    panel_pad: int = 40        # 板の、文字のまわりの余白
    panel_margin: int = 40     # 板の、画面の左右からの距離
    # fit：大きさを文ごとに選ぶ（上の大きさを上限に、不自然な折り返しをしない範囲でいちばん大きく）
    fit: bool = False
    hook_size: int = 0
    floor_ratio: float = 0.7   # 大きさの下限 = 上限 × この値
    # 行数の上限：今日の1文（日本語 / 英訳）、かたまり（日本語 / 意味）、メモ、問いかけ・予告
    sentence_lines: tuple[int, int] = (2, 3)
    chunk_lines: tuple[int, int] = (1, 2)
    note_lines: int = 3
    hook_lines: int = 3


def _bounds(events: list[Event]) -> tuple[float, float]:
    tops, bottoms = [], []
    for e in events:
        h = (e.size or 0) * 1.25 * len(e.lines)
        tops.append(e.y - h / 2)
        bottoms.append(e.y + h / 2)
    return min(tops), max(bottoms)


def build_lesson_events(
    timing: dict, story_hook: str, translation: str, breakdown: list[dict], next_text: str, *,
    lo: Layout, look: LessonLook, sub_y: int, label_y: int, hook_y: int, hook_max_chars: int,
    outro_label: str = "Next line",
) -> list[Event]:
    """レッスン形式：問いかけ → 今日の1文 → かたまりごとの分解 → まねする → 最後の一文（D-024）。

    最後の一文（next_text）は、作品の出典と背景（outro_label = About this story）か、次の1文の予告。

    timing["sentences"] の role（sentence / chunk / repeat）と、timing["lesson"] の
    shadow（まねする間）・next（予告）の時刻に合わせて画面を切り替える。
    画面ごとに文字の下へ半透明の板（Panel）を敷き、背景の写真に左右されずに読めるようにする。
    """
    steps = timing["sentences"]
    by_role = {r: [s for s in steps if s.get("role") == r] for r in ("sentence", "chunk", "repeat")}
    if not by_role["sentence"] or not by_role["repeat"]:
        raise AiShortsError("timing.json にレッスン形式の情報がありません。tts をやり直してください。")
    sentence, repeat = by_role["sentence"][0], by_role["repeat"][0]
    chunks = by_role["chunk"]
    shadow = timing["lesson"]["shadow"]
    nxt = timing["lesson"]["next"]
    events: list[Event] = []

    def screen(start: float, end: float, labels: list[tuple[str, float, float]],
               body: list[Event]) -> None:
        heads = [Event(round(a, 3), round(b, 3), "Label", [t], label_y, size=look.label_size)
                 for t, a, b in labels]
        top, bottom = _bounds(heads + body)
        top, bottom = round(top - look.panel_pad), round(bottom + look.panel_pad)
        w, h = lo.width - 2 * look.panel_margin, bottom - top
        events.append(Event(round(start, 3), round(end, 3), "Panel",
                            [f"m 0 0 l {w} 0 {w} {h} 0 {h}"], top, look.panel_margin, layer=0))
        events.extend(heads + body)

    avail = lo.width - 2 * (look.panel_margin + look.panel_pad)   # 板の内側の幅

    def floor(cap: int) -> int:
        return max(1, round(cap * look.floor_ratio))

    def english(text: str, cap: int, max_chars: int, max_lines: int) -> tuple[int, list[str]]:
        if not look.fit:
            return cap, word_wrap(text, max_chars)
        return fit_en(text, avail=avail, em=lo.em, cap=cap, floor=floor(cap), max_lines=max_lines)

    def block(text: str, en: str, start: float, end: float, base: Layout,
              lines: tuple[int, int]) -> tuple[list[Event], float]:
        if not look.fit:
            return ruby_block(text, en, start, end, sub_y, base)
        plain = ruby.strip(text).rstrip("。")
        size, max_chars = fit_ja(plain, avail=avail, em=base.em, cap=base.font_size,
                                 floor=floor(base.font_size), max_lines=lines[0])
        en_size, en_lines = english(en, base.en_size, base.en_max_chars, lines[1]) if en else (base.en_size, None)
        fitted = Layout(base.width, size, round(base.ruby_size * size / base.font_size), en_size,
                        max_chars, base.en_max_chars, base.em, base.gap)
        return ruby_block(text, en, start, end, sub_y, fitted, en_lines=en_lines)

    if story_hook and sentence["start"] > 0:
        hook_size, hook_lines = english(story_hook, look.hook_size or 0, hook_max_chars, look.hook_lines)
        events.append(Event(0.0, round(sentence["start"], 3), "Hook", hook_lines, hook_y,
                            size=hook_size if look.fit else None))
    first_chunk = chunks[0]["start"] if chunks else repeat["start"]
    screen(sentence["start"], first_chunk, [("Today's line", sentence["start"], first_chunk)],
           block(sentence["text"], translation, sentence["start"], first_chunk, lo, look.sentence_lines)[0])

    for i, c in enumerate(chunks):
        end = chunks[i + 1]["start"] if i + 1 < len(chunks) else repeat["start"]
        part = breakdown[c["index"]]
        body, bottom = block(part["ja"], part.get("en", ""), c["start"], end, look.chunk, look.chunk_lines)
        note = part.get("note", "")
        if note:
            note_size, note_lines = english(note, look.note_size, look.note_max_chars, look.note_lines)
            h = note_size * 1.25 * len(note_lines)
            body.append(Event(round(c["start"], 3), round(end, 3), "Note", note_lines,
                              round(bottom + note_size * 0.9 + h / 2), size=note_size))
        screen(c["start"], end, [(f"Breakdown {i + 1}/{len(chunks)}", c["start"], end)], body)

    screen(repeat["start"], shadow[1],
           [("Repeat after me", repeat["start"], shadow[0]), ("Your turn!", shadow[0], shadow[1])],
           block(repeat["text"], translation, repeat["start"], shadow[1], lo, look.sentence_lines)[0])
    if next_text:
        # 出典と背景は2文になることが多いので、5行まで
        next_size, next_lines = english(next_text, lo.en_size, lo.en_max_chars, 5)
        screen(nxt[0], nxt[1], [(outro_label, nxt[0], nxt[1])],
               [Event(round(nxt[0], 3), round(nxt[1], 3), "En", next_lines, sub_y, size=next_size)])
    return events


def _ass_time(sec: float) -> str:
    cs = int(round(sec * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_escape(text: str) -> str:
    return text.replace("\\", "＼").replace("{", "｛").replace("}", "｝")


def to_ass(events: list[Event], *, width: int, height: int, font_name: str,
           font_size: int, hook_font_size: int, outline: float,
           hook_box: bool = False, hook_box_opacity: float = 0.75, hook_box_padding: float = 36,
           ruby_size: int = 0, en_size: int = 0, label_size: int = 0,
           lesson: bool = False, panel_opacity: float = 0.6, label_pad: float = 22) -> str:
    style_fmt = ("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
                 "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
                 "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding")

    def style(name: str, size: int, border: float, box: bool = False,
              colour: str = "&H00FFFFFF", box_colour: str | None = None,
              pad: float | None = None) -> str:
        # BorderStyle 3 は縁取りの代わりに箱を描く（箱の色 = OutlineColour、Outline = 文字のまわりの余白）
        if box:
            alpha = round((1 - max(0.0, min(1.0, hook_box_opacity))) * 255)
            outline_colour = box_colour or f"&H{alpha:02X}000000"
            border_style, border = 3, hook_box_padding if pad is None else pad
        else:
            outline_colour, border_style = "&H00000000", 1
        return (f"Style: {name},{font_name},{size},{colour},&H000000FF,{outline_colour},&H64000000,"
                f"0,0,0,0,100,100,0,0,{border_style},{border:g},0,5,0,0,0,1")

    def lesson_styles() -> list[str]:
        # レッスン形式（D-024）：文字の下に板を敷くので、縁取りは細く。役割ごとに色を分ける（&HAABBGGRR）
        #   日本語 = 白 / ルビ = 白に近い黄 / 意味・英訳 = 黄 / 文法のメモ = 薄い緑 / 見出し = 藍の帯に白
        panel_alpha = round((1 - max(0.0, min(1.0, panel_opacity))) * 255)
        return [
            style("Ruby", ruby_size, 2.0, colour="&H00D6F2FF"),
            style("En", en_size, 2.5, colour="&H0066D9FF"),
            style("Note", round(en_size * 0.9), 2.5, colour="&H00C8F0A8"),
            style("Label", label_size, 0, True, box_colour="&H00A04A2E", pad=label_pad),
            f"Style: Panel,{font_name},10,&H{panel_alpha:02X}000000,&H000000FF,&H00000000,"
            "&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
        ]

    out = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}",
        "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]", style_fmt,
        style("Sub", font_size, 3.0 if lesson else outline),
        style("Hook", hook_font_size, outline * 1.5, hook_box),
        # 学習者向け：ルビは小さく、英訳は淡い黄色で日本語と見分ける（ASS の色は &HAABBGGRR）
        *([style("Ruby", ruby_size, max(2.0, outline * 0.6))] if ruby_size and not lesson else []),
        *([style("En", en_size, max(2.0, outline * 0.8), colour="&H00B4F0FF")]
          if en_size and not lesson else []),
        *(lesson_styles() if lesson else []),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for e in events:
        times = f"{_ass_time(e.start)},{_ass_time(e.end)}"
        if e.style == "Panel":
            # 図形（\p1）で板を描く。左上を (x, y) に置く
            out.append(f"Dialogue: {e.layer},{times},Panel,,0,0,0,,"
                       f"{{\\an7\\pos({e.x},{e.y})\\p1}}{e.lines[0]}{{\\p0}}")
            continue
        fade = r"\fad(0,250)" if e.style == "Hook" else ""
        fs = f"\\fs{e.size}" if e.size else ""
        text = r"\N".join(_ass_escape(line) for line in e.lines)
        x = width // 2 if e.x is None else e.x
        layer = max(e.layer, 1) if lesson else e.layer
        out.append(
            f"Dialogue: {layer},{times},{e.style},,0,0,0,,"
            f"{{\\an5\\pos({x},{e.y}){fs}{fade}}}{text}"
        )
    return "\n".join(out) + "\n"


def run(project: Project, story_id: str) -> None:
    work = project.root / "work" / story_id
    timing_path = work / "timing.json"
    if not timing_path.exists():
        raise AiShortsError(f"{timing_path} がありません。先に tts を実行してください。")
    timing = json.loads(timing_path.read_text(encoding="utf-8"))
    story = load_approved(project, story_id)

    width = int(project.get("render.width"))
    height = int(project.get("render.height"))
    font_size = int(project.get("subs.font_size"))
    hook_font_size = int(project.get("subs.hook_font_size"))
    lesson = project.get("format", "story") == "lesson"
    learner = lesson or project.get("subs.mode", "normal") == "learner"
    ruby_size = int(project.get("subs.ruby_font_size", 0)) if learner else 0
    en_size = int(project.get("subs.en_font_size", 0)) if learner else 0
    label_size = int(project.get("subs.label_font_size", 40)) if lesson else 0
    common = dict(
        max_chars=int(project.get("subs.max_chars_per_line")),
        sub_y=round(height * float(project.get("subs.position_y_ratio"))),
        hook_seconds=float(project.get("subs.hook_seconds")),
        hook_max_chars=int(project.get("subs.hook_max_chars_per_line")),
        hook_y=round(height * float(project.get("subs.hook_position_y_ratio"))),
    )
    if lesson:
        em = em_ratio(project.path(project.get("subs.font_file")))
        en_max = int(project.get("subs.en_max_chars_per_line"))
        lo = Layout(width, font_size, ruby_size, en_size, common["max_chars"], en_max, em)
        chunk_size = int(project.get("subs.chunk_font_size", font_size))
        look = LessonLook(
            label_size=label_size,
            note_size=int(project.get("subs.note_font_size", round(en_size * 0.9))),
            note_max_chars=int(project.get("subs.note_max_chars_per_line", en_max)),
            chunk=Layout(width, chunk_size,
                         int(project.get("subs.chunk_ruby_font_size", round(ruby_size * chunk_size / font_size))),
                         en_size, int(project.get("subs.chunk_max_chars_per_line", common["max_chars"])),
                         en_max, em),
            panel_pad=int(project.get("subs.panel_padding", 40)),
            panel_margin=int(project.get("subs.panel_margin", 40)),
            fit=bool(project.get("subs.fit", False)),
            hook_size=hook_font_size,
            floor_ratio=float(project.get("subs.fit_floor_ratio", 0.7)),
        )
        events = build_lesson_events(
            timing, story.hook, story.translations[0] if story.translations else "",
            story.breakdown, story.about or story.next, lo=lo, look=look, sub_y=common["sub_y"],
            outro_label="About this story" if story.about else "Next line",
            label_y=round(height * float(project.get("subs.label_position_y_ratio", 0.2))),
            hook_y=common["hook_y"], hook_max_chars=common["hook_max_chars"],
        )
    elif learner:
        events = build_learner_events(
            timing, story.translations, story.hook, width=width, font_size=font_size,
            ruby_size=ruby_size, en_size=en_size,
            en_max_chars=int(project.get("subs.en_max_chars_per_line")),
            em=em_ratio(project.path(project.get("subs.font_file"))), **common,
        )
    else:
        events = build_events(
            timing, story.hook, linger=float(project.get("subs.linger_seconds")),
            hook_alone=bool(project.get("subs.hook_alone", False)), **common,
        )
    ass = to_ass(
        events, width=width, height=height, font_name=project.get("subs.font_name"),
        font_size=font_size, hook_font_size=hook_font_size,
        outline=float(project.get("subs.outline")),
        hook_box=bool(project.get("subs.hook_box", False)),
        hook_box_opacity=float(project.get("subs.hook_box_opacity", 0.75)),
        hook_box_padding=float(project.get("subs.hook_box_padding", 36)),
        ruby_size=ruby_size, en_size=en_size, label_size=label_size,
        lesson=lesson, panel_opacity=float(project.get("subs.panel_opacity", 0.6)),
    )
    font_sizes = {"Sub": font_size, "Hook": hook_font_size}
    if learner:
        font_sizes.update({"Ruby": ruby_size, "En": en_size})
    if lesson:
        font_sizes.update({"Label": label_size, "Note": round(en_size * 0.9)})
    (work / "subs.ass").write_text(ass, encoding="utf-8")
    (work / "subs.json").write_text(
        json.dumps(
            {"width": width, "height": height,
             "font_size": font_sizes,
             # 全角1字の幅 / 文字の大きさ。QA が横幅を見積もるのに使う
             "em": em_ratio(project.path(project.get("subs.font_file"))),
             "events": [asdict(e) for e in events]},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    longest = max((len(line) for e in events for line in e.lines), default=0)
    print(f"[subs] {len(events)} 件（最長 {longest} 字/行）→ {work / 'subs.ass'}")
