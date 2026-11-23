"""字幕（subs）: work/{id}/timing.json → work/{id}/subs.ass, subs.json

文を1行 max_chars_per_line 字以内に区切り、文の時間を字数に比例して割り振る。
区切る位置は、句読点の後と「ひらがな → 漢字・カタカナ」の切れ目（文節の切れ目に近い）から選び、
行の長さがそろうようにする。「っ」の後（引っ越す）では切らず、漢字の前の「お」「ご」は次の語に付ける。
長いひらがなの続きは助詞の後で切り、「この」で行を終えたり漢字1字で行を始めたりしないようにする。冒頭 hook_seconds 秒は hook を大きく出す。
hook_alone なら hook は最初の文が始まるまでに消し、本文の字幕と重ねない（D-013）。
hook_box なら hook を半透明の帯で囲み、本文と見た目でも区別する。
subs.json は qa が行の長さと位置を検査するのに使う。
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import Project
from .errors import AiShortsError
from .story import load_approved

BREAK_AFTER = "、。，．！？!?」』）)…"
SMALL_KANA = "ぁぃぅぇぉっゃゅょゎ"
NO_LINE_START = BREAK_AFTER + "ー" + SMALL_KANA + "ァィゥェォッャュョヮ・"
OPEN_QUOTES, CLOSE_QUOTES = "「『", "」』"
# 漢字の前の「お」「ご」は接頭語として次の語に付ける（「迷子の｜お知らせ」「一階で｜お待ち」）。
PREFIXES = "おご"
# 送りがなの後に付いて一語になる漢字（生き物・話し方・置き場）。この前では切らない。
COMPOUND_TAILS = "物方場"
PARTICLES = "のがはをにでともへや"
# 漢字1字＋この送りがな1字＋漢字は、複合語として切らない（売れ残り・見上げた・思い出・吸い上げ）。
CONTINUATIVE = "いきしちひびみりぎじえけせねべめれげ"
# 長いひらがなの続きを字数で切るときは、この字の後を選ぶ（前の組ほど優先。「やって｜くるでしょう」「おいしく｜ありません」）。
SPLIT_AFTER_TIERS = ("てを", "にがはとも", "で", "く")
DETERMINERS = ("この", "その", "あの", "どの")
# 行の区切り方のコスト。行の余り字数 s に対して s + s²/max_chars（行が少なく、長さがそろうほど安い）に、次の罰を足す。
# 句読点以外で切ると、1行増やすより高くつくようにしてある（「背を｜測り」より「、」で切る）。
NOT_AT_PUNCT_PENALTY = 30
INSIDE_QUOTE_PENALTY = 25     # かぎかっこの途中で切る（「少し｜休んで」）
PARTICLE_START_PENALTY = 28   # 」のすぐ後の助詞で行が始まる（「勇気」｜を押した）
DETERMINER_END_PENALTY = 50   # 「この」「その」で行が終わる（今日が、この｜町の明日）
LONE_KANJI_START_PENALTY = 30  # 漢字1字と句読点だけで行が始まる（男の｜子。）
PAST_PERIOD_PENALTY = 30      # 行の中の「。」の後を句読点以外で切る（くるでしょう。娘の｜町の）


@dataclass
class Event:
    start: float
    end: float
    style: str
    lines: list[str]
    y: int


def _is_hiragana(c: str) -> bool:
    return "ぁ" <= c <= "ゟ"


def _is_kanji(c: str) -> bool:
    return "一" <= c <= "鿿" or c == "々"


def _split_long(a: str, max_chars: int) -> list[str]:
    """max_chars を超える単位を切る。行頭に来てはいけない字の前では切らず、ひらがなは助詞の後を選ぶ。

    助詞がなければ漢字 → ひらがなの切れ目（最後尾｜だったんですか）。どちらもなければ字数で切るが、
    どの切り方でも、次の行がかっこ・句読点を除いて2字以下になるもの（だったんです｜か」、
    うまって｜いる）は、ほかに切れ目があれば避ける。
    """
    result: list[str] = []
    while len(a) > max_chars:
        ks = [k for k in range(1, max_chars + 1) if a[k] not in NO_LINE_START]
        roomy = [k for k in ks if len(a[k:].rstrip(BREAK_AFTER)) > 2]
        cands = roomy or ks
        k = 0
        for tier in SPLIT_AFTER_TIERS:
            good = [k for k in cands if k >= 2 and a[k - 1] in tier and _is_hiragana(a[k])]
            if good:
                k = max(good)
                break
        if not k:
            good = [k for k in cands if _is_kanji(a[k - 1]) and _is_hiragana(a[k])]
            k = max(good) if good else 0
        if not k:
            k = max(cands) if cands else max_chars
        result.append(a[:k])
        a = a[k:]
    result.append(a)
    return result


def display_text(sentence: str) -> str:
    """字幕では文末の「。」を出さない（「。」」のようにかっこの中は残す）。"""
    return sentence.rstrip("。")


def atoms(text: str, max_chars: int) -> list[str]:
    """改行してよい位置で区切った最小単位。max_chars を超えるものはそこで切る。"""
    out: list[str] = []
    cur = ""
    for i, c in enumerate(text):
        cur += c
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if not nxt:
            break
        after = text[i + 2] if i + 2 < len(text) else ""
        # 語の頭の「お」「ご」（「お世話」「迷子の｜お知らせ」）。ひらがなの続きの中の「お」は除く
        is_prefix = c in PREFIXES and _is_kanji(nxt) and (len(cur) == 1 or not _is_hiragana(cur[-2]))
        # 漢字＋送りがな（1〜2字）＋「物」などは一語（生き物・落とし物）。助詞の後（犬が｜物を）は除く
        is_compound = (nxt in COMPOUND_TAILS and c not in PARTICLES
                       and any(_is_kanji(x) for x in cur[-3:-1])) or (
            c in CONTINUATIVE and _is_kanji(nxt) and len(cur) >= 2 and _is_kanji(cur[-2]))
        boundary = (c in BREAK_AFTER and nxt not in BREAK_AFTER) or (
            # 「っ」の後（引っ越す）と接頭語の後（お知らせ）では切らない
            _is_hiragana(c) and c not in SMALL_KANA and not is_prefix and not is_compound
            and not _is_hiragana(nxt) and nxt not in NO_LINE_START
        ) or (
            _is_hiragana(c) and nxt in PREFIXES and _is_kanji(after)
        )
        if boundary:
            out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    result: list[str] = []
    for a in out:
        result.extend(_split_long(a, max_chars))
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
        if parts[j - 1] in DETERMINERS:
            cost += DETERMINER_END_PENALTY
        head = parts[j].rstrip(BREAK_AFTER)
        if len(head) == 1 and _is_kanji(head) and head != parts[j]:
            cost += LONE_KANJI_START_PENALTY
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
            if j < n and parts[j - 1][-1] not in BREAK_AFTER and any("。" in p for p in parts[i:j]):
                cost += PAST_PERIOD_PENALTY
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
           hook_box: bool = False, hook_box_opacity: float = 0.75, hook_box_padding: float = 36) -> str:
    style_fmt = ("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
                 "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
                 "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding")

    def style(name: str, size: int, border: float, box: bool = False) -> str:
        # BorderStyle 3 は縁取りの代わりに箱を描く（箱の色 = OutlineColour、Outline = 文字のまわりの余白）
        if box:
            alpha = round((1 - max(0.0, min(1.0, hook_box_opacity))) * 255)
            outline_colour, border_style, border = f"&H{alpha:02X}000000", 3, hook_box_padding
        else:
            outline_colour, border_style = "&H00000000", 1
        return (f"Style: {name},{font_name},{size},&H00FFFFFF,&H000000FF,{outline_colour},&H64000000,"
                f"0,0,0,0,100,100,0,0,{border_style},{border:g},0,5,0,0,0,1")

    out = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}",
        "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]", style_fmt,
        style("Sub", font_size, outline), style("Hook", hook_font_size, outline * 1.5, hook_box), "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for e in events:
        fade = r"\fad(0,250)" if e.style == "Hook" else ""
        text = r"\N".join(_ass_escape(line) for line in e.lines)
        out.append(
            f"Dialogue: 0,{_ass_time(e.start)},{_ass_time(e.end)},{e.style},,0,0,0,,"
            f"{{\\an5\\pos({width // 2},{e.y}){fade}}}{text}"
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
    events = build_events(
        timing, story.hook,
        max_chars=int(project.get("subs.max_chars_per_line")),
        linger=float(project.get("subs.linger_seconds")),
        sub_y=round(height * float(project.get("subs.position_y_ratio"))),
        hook_seconds=float(project.get("subs.hook_seconds")),
        hook_max_chars=int(project.get("subs.hook_max_chars_per_line")),
        hook_y=round(height * float(project.get("subs.hook_position_y_ratio"))),
        hook_alone=bool(project.get("subs.hook_alone", False)),
    )
    ass = to_ass(
        events, width=width, height=height, font_name=project.get("subs.font_name"),
        font_size=font_size, hook_font_size=hook_font_size,
        outline=float(project.get("subs.outline")),
        hook_box=bool(project.get("subs.hook_box", False)),
        hook_box_opacity=float(project.get("subs.hook_box_opacity", 0.75)),
        hook_box_padding=float(project.get("subs.hook_box_padding", 36)),
    )
    (work / "subs.ass").write_text(ass, encoding="utf-8")
    (work / "subs.json").write_text(
        json.dumps(
            {"width": width, "height": height,
             "font_size": {"Sub": font_size, "Hook": hook_font_size},
             "events": [asdict(e) for e in events]},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    longest = max((len(line) for e in events for line in e.lines), default=0)
    print(f"[subs] {len(events)} 件（最長 {longest} 字/行）→ {work / 'subs.ass'}")
