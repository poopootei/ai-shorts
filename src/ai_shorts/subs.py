"""字幕（subs）: work/{id}/timing.json → work/{id}/subs.ass, subs.json

文を1行 max_chars_per_line 字以内に区切り、文の時間を字数に比例して割り振る。
区切る位置は、句読点の後と「ひらがな → 漢字・カタカナ」の切れ目（文節の切れ目に近い）から選び、
行の長さがそろうようにする。冒頭 hook_seconds 秒は hook を大きく出す。
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


def _is_hiragana(c: str) -> bool:
    return "ぁ" <= c <= "ゟ"


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
    hook_seconds: float, hook_max_chars: int, hook_y: int,
) -> list[Event]:
    events: list[Event] = []
    if hook and hook_seconds > 0:
        events.append(Event(0.0, hook_seconds, "Hook", wrap(hook, hook_max_chars), hook_y))

    sentences = timing["sentences"]
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
           font_size: int, hook_font_size: int, outline: float) -> str:
    style_fmt = ("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
                 "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
                 "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding")

    def style(name: str, size: int, border: float) -> str:
        return (f"Style: {name},{font_name},{size},&H00FFFFFF,&H000000FF,&H00000000,&H64000000,"
                f"0,0,0,0,100,100,0,0,1,{border:g},0,5,0,0,0,1")

    out = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}",
        "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]", style_fmt,
        style("Sub", font_size, outline), style("Hook", hook_font_size, outline * 1.5), "",
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
    )
    ass = to_ass(
        events, width=width, height=height, font_name=project.get("subs.font_name"),
        font_size=font_size, hook_font_size=hook_font_size,
        outline=float(project.get("subs.outline")),
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
