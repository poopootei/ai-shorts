"""物語 JSON を検査する（字数・文の長さ・hook・段落と画像の数・声）。--readings で読みも確かめる。

    python scripts/check_story.py 20261120-001            # stories/draft か approved から探す
    python scripts/check_story.py stories/draft/*.json     # 複数可
    python scripts/check_story.py 20261120-001 --readings # 声のエンジンで読みを出す（エンジン起動が必要）

決まり（docs/story-guidelines.md）に合わないものを「NG」、気にしたほうがよいものを「注意」で出す。
NG が1つでもあれば終了コード 1。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ai_shorts.config import add_channel_arg, script_root  # noqa: E402

ROOT = script_root()  # チャンネルのフォルダ（channels/{name}/）。--channel で選ぶ

from ai_shorts import ruby, userdict, voices  # noqa: E402
from ai_shorts.config import load_project  # noqa: E402
from ai_shorts.errors import AiShortsError  # noqa: E402
from ai_shorts.story import VISUALS, split_paragraphs, split_sentences  # noqa: E402
from ai_shorts.tts import tts_text  # noqa: E402

# 既定は今のチャンネル（docs/story-guidelines.md）。チャンネルごとに config の story.* で変える
BODY_MIN, BODY_MAX = 250, 280
SENTENCE_MAX = 40
HOOK_MAX = 15
REQUIRED = ("id", "title", "hook", "body", "image_prompts", "tags", "approved")


def limits(project) -> tuple[int, int, int, int]:
    return (int(project.get("story.body_min_chars", BODY_MIN)),
            int(project.get("story.body_max_chars", BODY_MAX)),
            int(project.get("story.sentence_max_chars", SENTENCE_MAX)),
            int(project.get("story.hook_max_chars", HOOK_MAX)))


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
    body_min, body_max, sentence_max, hook_max = limits(project)
    lesson = project.get("format", "story") == "lesson"
    learner = lesson or project.get("subs.mode", "normal") == "learner"
    paras = split_paragraphs(d.get("body", ""))
    n = sum(len(ruby.strip(p)) for p in paras)
    sentences = [s for p in paras for s in split_sentences(p)]
    longest = max((ruby.strip(s) for s in sentences), key=len) if sentences else ""
    chunks = [c.get("ja", "") for c in d.get("breakdown", [])]
    if lesson:
        # レッスン形式（D-024）：1本で1文。かたまりに分けて、つなげると元の文になる
        if len(sentences) != 1:
            ng.append(f"本文が {len(sentences)} 文（レッスン形式は1文）")
        if not 2 <= len(chunks) <= 5:
            ng.append(f"かたまり（breakdown）が {len(chunks)} 個（2〜5）")
        if any(not c.get("ja") or not c.get("en") for c in d.get("breakdown", [])):
            ng.append("breakdown に ja か en のないものがある")
        drop = str.maketrans("", "", "、。「」『』！？")
        joined = "".join(ruby.strip(c) for c in chunks).translate(drop)
        if sentences and joined != ruby.strip(sentences[0]).translate(drop):
            ng.append(f"かたまりをつなげても本文にならない: {joined}")
        if len(d.get("image_prompts", [])) != 3:
            warn.append("image_prompts は3つ（今日の1文 / 分解 / まねる）")
    else:
        if not body_min <= n <= body_max:
            (ng if n > body_max + 10 or n < body_min - 40 else warn).append(f"本文 {n} 字（目安 {body_min}〜{body_max}）")
        if not 2 <= len(paras) <= 3:
            ng.append(f"段落 {len(paras)} 個（2〜3）")
        if d.get("visual") != "3d" and len(d.get("image_prompts", [])) != len(paras):
            warn.append(f"image_prompts {len(d.get('image_prompts', []))} 個と段落 {len(paras)} 個の数が違う")
    if d.get("visual", "") not in VISUALS:
        ng.append(f"visual は {' / '.join(repr(v) for v in VISUALS)} のどれか（{d.get('visual')!r}）")
    if len(longest) > sentence_max:
        ng.append(f"{sentence_max} 字を超える文がある（{len(longest)} 字）: {longest}")
    if len(d.get("hook", "")) > hook_max:
        ng.append(f"hook {len(d['hook'])} 字（{hook_max} 字以内）")
    if learner:
        # 学習者向け：すべての漢字にルビ、文ごとに英訳（docs/decisions.md D-022）
        bare = sorted({c for s in sentences + chunks for c in ruby.uncovered_kanji(s)})
        if bare:
            ng.append(f"ルビのない漢字がある: {''.join(bare)}")
        tr = d.get("translations", [])
        if len(tr) != len(sentences):
            ng.append(f"英訳 {len(tr)} 文と本文 {len(sentences)} 文の数が違う")
        elif any(not t.strip() for t in tr):
            ng.append("空の英訳がある")
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
          f" / 声 {voice.key + '（' + voice.credit + '）' if voice else '?'}"
          f" / 映像 {'3D' if d.get('visual') == '3d' else '静止画'}")
    for m in ng:
        print(f"   NG   {m}")
    for m in warn:
        print(f"   注意 {m}")

    if readings and voice:
        client = voices.connect(voice, userdict.load(project.path(project.get("tts.user_dict"))), lambda m: None)
        print("   読み（/ はアクセント句の区切り。VOICEVOX 互換は ' がアクセント位置）:")
        mismatched = []
        for s in sentences + chunks:
            text = tts_text(s)
            if voice.engine_type == "coeiroink":
                r = client.reading(text)
            else:
                r = client.audio_query(text, voice.style_id)["kana"]
            print(f"     {s}\n       → {r}")
            if learner:
                mismatched += ruby.missing_readings(s, r)
        if mismatched:
            # 学習者は読みをそのまま覚えるので、ルビと読み上げが違うものは出さない
            print(f"   NG   読み上げがルビと違う（辞書で直すか、ルビを直す）: {' '.join(mismatched)}")
            ng.append("読み上げがルビと違う")
    return 1 if ng else 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_channel_arg(ap)
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
