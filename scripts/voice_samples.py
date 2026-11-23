"""声の聞き比べ用サンプルを作る。同じ文章を声ごとに読ませ、1本につなげた wav も作る。

    # config に登録済みの声で
    python scripts/voice_samples.py --id 20261119-002 --paragraph 2 ofutonp aida tsukuyomi
    # 登録前の声も試せる（エンジン名:スタイル ID）
    python scripts/voice_samples.py --id 20261119-002 --paragraph 2 coeiroink:9 aivisspeech:1310138977

出力は work/voice_samples/（声ごとの wav と 00_all.wav）。端末に、つなげた wav の中の時刻を出す。
話速は声の speed（未登録なら tts.speed）。ユーザー辞書も反映してから読ませる。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ai_shorts import userdict, voices  # noqa: E402
from ai_shorts.config import add_channel_arg, load_project, script_root  # noqa: E402
from ai_shorts.story import load_approved  # noqa: E402
from ai_shorts.tts import VoiceSettings, build_segments, synthesize_story  # noqa: E402

SR = 48000


def voice_for(project, spec: str) -> voices.Voice:
    if ":" not in spec:
        return voices.resolve(project, spec)
    engine, style = spec.split(":", 1)
    eng = project.get(f"engines.{engine}")
    return voices.Voice(key=spec.replace(":", "_"), engine=engine, engine_type=eng["type"], url=eng["url"],
                        style_id=int(style), credit="(未登録)", speed=float(project.get("tts.speed")),
                        speed_max=float(project.get("tts.speed")), intonation_scale=1.0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_channel_arg(ap)
    ap.add_argument("voices", nargs="+", help="voices のキー、または エンジン名:スタイルID")
    ap.add_argument("--id", required=True, help="文章を取る物語（承認済み）")
    ap.add_argument("--paragraph", type=int, default=1, help="何段落目を読ませるか（1から）")
    args = ap.parse_args()

    project = load_project(script_root())
    para = load_approved(project, args.id).paragraphs[args.paragraph - 1]
    segs = build_segments([para])
    words = userdict.load(project.path(project.get("tts.user_dict")))
    out = project.root / "work" / "voice_samples"
    out.mkdir(parents=True, exist_ok=True)
    pcm, t = [], 0.0
    for i, spec in enumerate(args.voices, start=1):
        v = voice_for(project, spec)
        client = voices.connect(v, words, lambda m: None)
        s = VoiceSettings(speaker_id=v.style_id, sample_rate=SR, pause_sentence=0.3, pause_paragraph=0.6,
                          pre_silence=0.3, post_silence=0.3, intonation_scale=v.intonation_scale)
        audio, *_ = synthesize_story(client, segs, s, [v.speed], max_seconds=999, log=lambda m: None)
        name = f"{i:02d}_{v.key}"
        sf.write(out / f"{name}.wav", audio, SR, subtype="PCM_16")
        print(f"{int(t // 60)}:{t % 60:04.1f}  {name}（{len(audio) / SR:.1f} 秒）")
        pcm += [audio, np.zeros(int(1.2 * SR), np.float32)]
        t += len(audio) / SR + 1.2
    sf.write(out / "00_all.wav", np.concatenate(pcm), SR, subtype="PCM_16")
    print(out / "00_all.wav")


if __name__ == "__main__":
    main()
