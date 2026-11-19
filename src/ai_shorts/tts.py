"""音声（tts）: stories/approved/{id}.json → work/{id}/voice.wav, timing.json

文ごとに合成し、文の間に無音を挟んでつなぐ。長さが上限を超えたら話速を上げて作り直す。
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from typing import Any, Callable, Protocol

import numpy as np
import soundfile as sf

from . import userdict, voices
from .config import Project
from .errors import ExternalToolError, StoryTooLongError
from .story import load_approved, split_sentences

SPEED_STEP = 0.03


class TtsClient(Protocol):
    def audio_query(self, text: str, speaker: int) -> dict[str, Any]: ...
    def synthesis(self, query: dict[str, Any], speaker: int) -> bytes: ...


@dataclass(frozen=True)
class Segment:
    text: str
    paragraph: int


@dataclass(frozen=True)
class VoiceSettings:
    speaker_id: int
    sample_rate: int
    pause_sentence: float
    pause_paragraph: float
    pre_silence: float
    post_silence: float
    intonation_scale: float = 1.0


def tts_text(sentence: str) -> str:
    """読み上げ用の文。VOICEVOX はかぎかっこの前後に間を入れてしまうので外す。
    「勇気」「眠り」のように並んだものは読点でつなぐ（字幕には元の文を使う）。"""
    for a, b in (("」「", "、"), ("』『", "、")):
        sentence = sentence.replace(a, b)
    return sentence.translate(str.maketrans("", "", "「」『』"))


def build_segments(paragraphs: list[str]) -> list[Segment]:
    return [
        Segment(text=s, paragraph=pi)
        for pi, para in enumerate(paragraphs)
        for s in split_sentences(para)
    ]


def speed_candidates(start: float, maximum: float, step: float = SPEED_STEP) -> list[float]:
    """start から step 刻みで maximum まで。最後は maximum ちょうどで終える。"""
    speeds = [round(start, 2)]
    while speeds[-1] < maximum - 1e-9:
        speeds.append(round(min(speeds[-1] + step, maximum), 2))
    return speeds


def assemble(
    segments: list[Segment],
    clips: list[np.ndarray],
    settings: VoiceSettings,
) -> tuple[np.ndarray, list[dict[str, Any]], list[dict[str, Any]]]:
    """文ごとの音声を無音でつなぎ、文と段落の開始・終了時刻を返す。"""
    sr = settings.sample_rate

    def silence(sec: float) -> np.ndarray:
        return np.zeros(int(round(sec * sr)), dtype=np.float32)

    pieces = [silence(settings.pre_silence)]
    cursor = len(pieces[0])
    sentences: list[dict[str, Any]] = []
    for i, (seg, clip) in enumerate(zip(segments, clips, strict=True)):
        if i > 0:
            gap = (
                settings.pause_paragraph
                if seg.paragraph != segments[i - 1].paragraph
                else settings.pause_sentence
            )
            pieces.append(silence(gap))
            cursor += len(pieces[-1])
        start = cursor
        pieces.append(clip.astype(np.float32))
        cursor += len(clip)
        sentences.append(
            {
                "index": i,
                "paragraph": seg.paragraph,
                "text": seg.text,
                "start": round(start / sr, 3),
                "end": round(cursor / sr, 3),
            }
        )
    pieces.append(silence(settings.post_silence))
    audio = np.concatenate(pieces)

    paragraphs: list[dict[str, Any]] = []
    for s in sentences:
        if paragraphs and paragraphs[-1]["index"] == s["paragraph"]:
            paragraphs[-1]["end"] = s["end"]
        else:
            paragraphs.append({"index": s["paragraph"], "start": s["start"], "end": s["end"]})
    return audio, sentences, paragraphs


def synthesize_story(
    client: TtsClient,
    segments: list[Segment],
    settings: VoiceSettings,
    speeds: list[float],
    max_seconds: float,
    log: Callable[[str], None] = print,
) -> tuple[np.ndarray, float, list[dict[str, Any]], list[dict[str, Any]]]:
    queries = [client.audio_query(tts_text(seg.text), settings.speaker_id) for seg in segments]
    duration = 0.0
    for speed in speeds:
        clips = [_synthesize(client, q, speed, settings) for q in queries]
        audio, sentences, paragraphs = assemble(segments, clips, settings)
        duration = len(audio) / settings.sample_rate
        log(f"speed {speed:.2f}: {duration:.2f} 秒")
        if duration <= max_seconds:
            return audio, speed, sentences, paragraphs
    raise StoryTooLongError(
        f"音声が {duration:.1f} 秒あり、上限 {max_seconds} 秒を超えています"
        f"（話速 {speeds[-1]:.2f} でも収まりません）。本文を短くしてください。"
    )


def _synthesize(
    client: TtsClient, query: dict[str, Any], speed: float, settings: VoiceSettings
) -> np.ndarray:
    # prePhonemeLength / postPhonemeLength はエンジンの既定（0.1秒）のまま。
    # 0 にすると文の頭が急に始まり、不自然に聞こえる。
    q = dict(
        query,
        speedScale=speed,
        intonationScale=settings.intonation_scale,
        outputSamplingRate=settings.sample_rate,
        outputStereo=False,
    )
    data, sr = sf.read(io.BytesIO(client.synthesis(q, settings.speaker_id)), dtype="float32")
    if sr != settings.sample_rate:
        raise ExternalToolError(
            f"VOICEVOX の出力が {sr} Hz でした（{settings.sample_rate} Hz を指定）。"
        )
    if data.ndim > 1:
        data = data.mean(axis=1)
    return data


def run(project: Project, story_id: str, client: TtsClient | None = None) -> None:
    def log(msg: str) -> None:
        print(f"[tts] {msg}")

    story = load_approved(project, story_id)
    segments = build_segments(story.paragraphs)
    if not segments:
        raise StoryTooLongError(f"{story_id} の本文が空です。")

    voice = voices.resolve(project, story.voice or None)
    pause = float(project.get("tts.pause_between_sentences"))
    settings = VoiceSettings(
        speaker_id=voice.style_id,
        sample_rate=int(project.get("tts.sample_rate", 48000)),
        pause_sentence=pause,
        pause_paragraph=float(project.get("tts.pause_between_paragraphs", pause)),
        pre_silence=float(project.get("tts.pre_silence")),
        post_silence=float(project.get("tts.post_silence")),
        intonation_scale=voice.intonation_scale,
    )
    speeds = speed_candidates(voice.speed, voice.speed_max)
    max_seconds = float(project.get("tts.max_voice_seconds"))
    if client is None:
        words = userdict.load(project.path(project.get("tts.user_dict")))
        client = voices.connect(voice, words, log)

    log(f"{story_id}: 声 {voice.key}（{voice.credit}）, {len(story.paragraphs)} 段落, {len(segments)} 文")
    audio, speed, sentences, paragraphs = synthesize_story(
        client, segments, settings, speeds, max_seconds, log
    )

    out = project.work_dir(story_id)
    sf.write(out / "voice.wav", audio, settings.sample_rate, subtype="PCM_16")
    timing = {
        "story_id": story_id,
        "voice": voice.key,
        "engine": voice.engine,
        "style_id": voice.style_id,
        "credit": voice.credit,
        "speed": speed,
        "intonation_scale": settings.intonation_scale,
        "sample_rate": settings.sample_rate,
        "duration": round(len(audio) / settings.sample_rate, 3),
        "paragraphs": paragraphs,
        "sentences": sentences,
    }
    (out / "timing.json").write_text(
        json.dumps(timing, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"→ {out / 'voice.wav'}（{len(audio) / settings.sample_rate:.2f} 秒, 話速 {speed:.2f}）")
