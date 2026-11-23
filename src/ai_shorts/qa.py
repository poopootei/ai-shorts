"""検査（qa）: work/{id}/video.mp4 を検査し、合格したら ready/{id}.mp4 にコピーする。

結果は work/{id}/qa.json。投稿用の説明文 work/{id}/description.txt もここで作る。
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import pyloudnorm as pyln
import soundfile as sf

from . import ffmpeg
from .config import Project
from .errors import AiShortsError, StoryError
from .story import Story, load_approved


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


def log(msg: str) -> None:
    print(f"[qa] {msg}")


_LABELS = {
    "ja": {"source": "出典：", "voice": "声：", "images": "背景画像："},
    "en": {"source": "Source: ", "voice": "Voice: ", "images": "Background images: "},
}


def describe(story: Story, credit: str, images: dict | None, lang: str = "ja") -> str:
    label = _LABELS.get(lang, _LABELS["ja"])
    lines = [story.title, "", story.hook, ""]
    if story.tags:
        lines += [" ".join(f"#{t}" for t in story.tags), ""]
    if story.source:
        lines.append(f"{label['source']}{story.source}")
    lines.append(f"{label['voice']}{credit}")
    if images and images.get("images"):
        sources = sorted({i.get("source") or "?" for i in images["images"]})
        licenses = sorted({(i.get("license") or "?").upper() for i in images["images"]})
        lines.append(f"{label['images']}{' / '.join(licenses)}（{', '.join(sources)}）")
    return "\n".join(lines) + "\n"


def text_width(line: str, size: int, em: float = 1.0) -> float:
    """字幕1行の幅の見積もり。全角（日本語）は1字 = size × em、半角（英語）はその約 0.6 倍。
    em は全角1字の幅 / 文字の大きさ（subs.json の em。フォントで決まる）。"""
    return sum(1.0 if ord(c) >= 0x2E80 else 0.6 for c in line) * size * em


def check_subs(subs: dict, *, max_chars: int | None, hook_max_chars: int | None, margin: int,
               bottom_ratio: float, en_max_chars: int | None = None) -> Check:
    width, height = subs["width"], subs["height"]
    limits = {"Sub": max_chars, "Hook": hook_max_chars, "En": en_max_chars,
              "Note": None, "Ruby": None, "Label": None}
    em = float(subs.get("em", 1.0))
    problems = []
    for e in subs["events"]:
        if e["style"] == "Panel":     # 文字の下に敷く板（文字ではない）
            continue
        size = e.get("size") or subs["font_size"][e["style"]]
        limit = limits.get(e["style"], max_chars)
        block = size * 1.25 * len(e["lines"])
        x = e.get("x") or width / 2
        for line in e["lines"]:
            if limit is not None and len(line) > limit:
                problems.append(f"{len(line)}字 > {limit}: {line}")
            half = text_width(line, size, em) / 2
            if x - half < margin or x + half > width - margin:
                problems.append(f"横にはみ出す（{round(half * 2)}px）: {line}")
        if e["y"] - block / 2 < 0 or e["y"] + block / 2 > height * (1 - bottom_ratio):
            problems.append(f"位置が安全な範囲の外（y={e['y']}）: {''.join(e['lines'])}")
    n = sum(len(e["lines"]) for e in subs["events"])
    return Check("字幕", not problems, "; ".join(problems[:5]) or f"{n} 行すべて範囲内")


def measure_lufs(video: Path, work: Path) -> float:
    tmp = work / "qa_audio.wav"
    try:
        ffmpeg.run(["-i", str(video), "-vn", "-ac", "2", "-c:a", "pcm_f32le", str(tmp)])
        data, sr = sf.read(tmp, dtype="float32")
        return float(pyln.Meter(sr).integrated_loudness(data))
    finally:
        tmp.unlink(missing_ok=True)


def run(project: Project, story_id: str) -> None:
    work = project.root / "work" / story_id
    video = work / "video.mp4"
    if not video.exists():
        raise AiShortsError(f"{video} がありません。先に render を実行してください。")

    checks: list[Check] = []

    try:
        story = load_approved(project, story_id)
        checks.append(Check("承認", True, "approved: true"))
    except StoryError as e:
        story = None
        checks.append(Check("承認", False, str(e)))

    info = ffmpeg.probe(video)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    duration = float(info["format"]["duration"])
    max_seconds = float(project.get("render.max_video_seconds"))
    checks.append(Check("長さ", duration <= max_seconds, f"{duration:.2f} 秒（上限 {max_seconds}）"))

    w, h = int(project.get("render.width")), int(project.get("render.height"))
    checks.append(Check("解像度", (v["width"], v["height"]) == (w, h),
                        f"{v['width']}x{v['height']}（期待 {w}x{h}）"))

    target = float(project.get("render.target_lufs"))
    tol = float(project.get("qa.lufs_tolerance"))
    lufs = measure_lufs(video, work)
    checks.append(Check("音量", abs(lufs - target) <= tol, f"{lufs:.1f} LUFS（{target}±{tol}）"))

    subs_path = work / "subs.json"
    if subs_path.exists():
        # subs.fit（大きさを文ごとに選ぶ）では、1行の字数は大きさで変わるので、横幅だけで検査する
        fit = bool(project.get("subs.fit", False))
        checks.append(check_subs(
            json.loads(subs_path.read_text(encoding="utf-8")),
            max_chars=None if fit else int(project.get("subs.max_chars_per_line")),
            hook_max_chars=None if fit else int(project.get("subs.hook_max_chars_per_line")),
            margin=int(project.get("qa.subs_side_margin")),
            bottom_ratio=float(project.get("qa.subs_bottom_ratio")),
            en_max_chars=None if fit else project.get("subs.en_max_chars_per_line", None),
        ))
    else:
        checks.append(Check("字幕", False, "subs.json がありません（subs を実行してください）"))

    # 声のクレジットは tts が timing.json に書いたもの（声ごとに違う）
    timing = json.loads((work / "timing.json").read_text(encoding="utf-8"))
    credit = timing.get("credit", "")
    images_path = work / "images.json"
    images = json.loads(images_path.read_text(encoding="utf-8")) if images_path.exists() else None
    description = work / "description.txt"
    if story and credit:
        description.write_text(
            describe(story, credit, images, lang=project.get("qa.description_lang", "ja")),
            encoding="utf-8",
        )
    credit_ok = bool(credit) and description.exists() and credit in description.read_text(encoding="utf-8")
    checks.append(Check("クレジット", credit_ok,
                        f"説明文に {credit}" if credit_ok
                        else f"説明文に声のクレジット（{credit or 'timing.json に記録なし'}）がありません"))

    passed = all(c.passed for c in checks)
    (work / "qa.json").write_text(
        json.dumps({"passed": passed, "checks": [asdict(c) for c in checks]},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for c in checks:
        log(f"{'OK ' if c.passed else 'NG '} {c.name}: {c.detail}")

    ready = project.root / "ready"
    ready.mkdir(exist_ok=True)
    dst = ready / f"{story_id}.mp4"
    if not passed:
        dst.unlink(missing_ok=True)  # 古い合格品を残さない
        raise AiShortsError(f"{story_id} は QA に通りませんでした（{work / 'qa.json'}）。")
    shutil.copy2(video, dst)
    shutil.copy2(description, ready / f"{story_id}.txt")
    log(f"合格 → {dst}")
