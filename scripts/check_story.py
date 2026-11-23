"""物語 JSON を検査する（字数・文の長さ・hook・段落と画像の数・声）。--readings で読みも確かめる。

    python scripts/check_story.py 20261120-001            # stories/draft か approved から探す
    python scripts/check_story.py stories/draft/*.json     # 複数可
    python scripts/check_story.py 20261120-001 --readings # 声のエンジンで読みを出す（エンジン起動が必要）

決まり（docs/story-guidelines.md）に合わないものを「NG」、気にしたほうがよいものを「注意」で出す。
NG が1つでもあれば終了コード 1。
"""

from __future__ import annotations

import argparse
import os
import json
import sys
from pathlib import Path

ROOT = Path(os.environ.get("AI_SHORTS_ROOT") or Path(__file__).resolve().parents[1]).resolve()  # チャンネルごとの作業場所（channels/{name}/）
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ai_shorts import userdict, voices  # noqa: E402
from ai_shorts.config import load_project  # noqa: E402
from ai_shorts.errors import AiShortsError  # noqa: E402
from ai_shorts.story import split_paragraphs, split_sentences  # noqa: E402
from ai_shorts.tts import tts_text  # noqa: E402

BODY_MIN, BODY_MAX = 250, 280
SENTENCE_MAX = 40
HOOK_MAX = 15
REQUIRED = ("id", "title", "hook", "body", "image_prompts", "tags", "approved")


def find(arg: str) -> Path:
    p = Path(arg)
    if p.suffix == ".json" and p.exists():
        return p
    for d in ("draft", "approved"):
        q = ROOT / "stories" / d / f"{arg}.json"
        if q.exists():
            return q
    raise SystemExit(f"物語が見つかりません: {arg}")


def check(path: Path, project, readings: bool) -> int:
    d = json.loads(path.read_text(encoding="utf-8"))
    ng, warn = [], []
    for k in REQUIRED:
        if k not in d:
            ng.append(f"項目 {k} がない")
    if d.get("id") != path.stem:
        ng.append(f"id（{d.get('id')}）とファイル名（{path.stem}）が違う")
    paras = split_paragraphs(d.get("body", ""))
    n = sum(len(p) for p in paras)
    sentences = [s for p in paras for s in split_sentences(p)]
    longest = max(sentences, key=len) if sentences else ""
    if not BODY_MIN <= n <= BODY_MAX:
        (ng if n > BODY_MAX + 10 or n < BODY_MIN - 40 else warn).append(f"本文 {n} 字（目安 {BODY_MIN}〜{BODY_MAX}）")
    if not 2 <= len(paras) <= 3:
        ng.append(f"段落 {len(paras)} 個（2〜3）")
    if len(d.get("image_prompts", [])) != len(paras):
        warn.append(f"image_prompts {len(d.get('image_prompts', []))} 個と段落 {len(paras)} 個の数が違う")
    if len(longest) > SENTENCE_MAX:
        ng.append(f"{SENTENCE_MAX} 字を超える文がある（{len(longest)} 字）: {longest}")
    if len(d.get("hook", "")) > HOOK_MAX:
        ng.append(f"hook {len(d['hook'])} 字（{HOOK_MAX} 字以内）")
    voice = None
    try:
        voice = voices.resolve(project, d.get("voice") or None)
    except AiShortsError as e:
        ng.append(str(e))
    if path.parent.name == "approved" and d.get("approved") is not True:
        ng.append("approved/ にあるのに approved: true ではない")
    if path.parent.name == "draft" and d.get("approved") is True:
        ng.append("draft/ にあるのに approved: true になっている（承認は scripts/approve_story.py で）")

    print(f"== {d.get('id')}「{d.get('title')}」 {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
    print(f"   本文 {n} 字 / 段落 {len(paras)} / 文 {len(sentences)}（最長 {len(longest)} 字）/ hook {len(d.get('hook', ''))} 字"
          f" / 声 {voice.key + '（' + voice.credit + '）' if voice else '?'}")
    for m in ng:
        print(f"   NG   {m}")
    for m in warn:
        print(f"   注意 {m}")

    if readings and voice:
        client = voices.connect(voice, userdict.load(project.path(project.get("tts.user_dict"))), lambda m: None)
        print("   読み（/ はアクセント句の区切り。VOICEVOX 互換は ' がアクセント位置）:")
        for s in sentences:
            text = tts_text(s)
            if voice.engine_type == "coeiroink":
                r = client.reading(text)
            else:
                r = client.audio_query(text, voice.style_id)["kana"]
            print(f"     {s}\n       → {r}")
    return 1 if ng else 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stories", nargs="+", help="物語の id か JSON のパス")
    ap.add_argument("--readings", action="store_true", help="声のエンジンで読みを出す")
    args = ap.parse_args()
    project = load_project(ROOT)
    rc = 0
    for s in args.stories:
        rc |= check(find(s), project, args.readings)
    sys.exit(rc)


if __name__ == "__main__":
    main()
