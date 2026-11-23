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

from . import ruby, userdict, voices
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
    「勇気」「眠り」のように並んだものは読点でつなぐ（字幕には元の文を使う）。
    ルビ（地獄《じごく》）は外して漢字で読ませる（読みが合っているかは check_story で確かめる）。"""
    sentence = ruby.strip(sentence)
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
    if project.get("format", "story") == "lesson":
        run_lesson(project, story, client, log)
        return
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


# ---- レッスン形式（format: lesson、D-024） -----------------------------------

@dataclass(frozen=True)
class LessonStep:
    role: str        # sentence（普通の速さ）/ chunk（かたまり）/ repeat（ゆっくり）
    text: str
    speed: float
    hold: float      # 読み終わってから次までの間（画面の英語を読む時間）
    index: int = 0   # chunk のとき、breakdown の何番目か


def lesson_steps(sentence: str, breakdown: list[dict], cfg: dict[str, float]) -> list[LessonStep]:
    """今日の1文 → かたまりごと → もう一度ゆっくり、の順の読み上げ。"""
    steps = [LessonStep("sentence", sentence, cfg["normal_speed"], cfg["sentence_hold"])]
    steps += [LessonStep("chunk", c["ja"], cfg["slow_speed"], cfg["chunk_hold"], i)
              for i, c in enumerate(breakdown)]
    steps.append(LessonStep("repeat", sentence, cfg["slow_speed"], 0.0))
    return steps


def assemble_lesson(
    steps: list[LessonStep], clips: list[np.ndarray], sample_rate: int, *,
    pre_silence: float, shadow_ratio: float, next_seconds: float,
) -> tuple[np.ndarray, list[dict[str, Any]], list[dict[str, Any]], dict[str, list[float]]]:
    """読み上げを間でつなぐ。最後の「ゆっくり」のあとに、まねする間（読み上げの長さ × shadow_ratio）と
    予告の時間を足す。画像は 文 / 分解 / まねる・予告 の3つの区間で切り替える（paragraphs）。"""
    sr = sample_rate
    pieces = [np.zeros(int(round(pre_silence * sr)), dtype=np.float32)]
    cursor = len(pieces[0])
    entries: list[dict[str, Any]] = []
    for step, clip in zip(steps, clips, strict=True):
        start = cursor
        pieces.append(clip.astype(np.float32))
        cursor += len(clip)
        entries.append({"role": step.role, "index": step.index, "text": step.text,
                        "paragraph": {"sentence": 0, "chunk": 1, "repeat": 2}[step.role],
                        "start": round(start / sr, 3), "end": round(cursor / sr, 3)})
        if step.hold > 0:
            pieces.append(np.zeros(int(round(step.hold * sr)), dtype=np.float32))
            cursor += len(pieces[-1])
    repeat = entries[-1]
    shadow_len = (repeat["end"] - repeat["start"]) * shadow_ratio
    tail = np.zeros(int(round((shadow_len + next_seconds) * sr)), dtype=np.float32)
    pieces.append(tail)
    total = (cursor + len(tail)) / sr
    shadow = [repeat["end"], round(repeat["end"] + shadow_len, 3)]
    lesson = {"shadow": shadow, "next": [shadow[1], round(total, 3)]}
    paragraphs: list[dict[str, Any]] = []
    for e in entries:
        if paragraphs and paragraphs[-1]["index"] == e["paragraph"]:
            paragraphs[-1]["end"] = e["end"]
        else:
            paragraphs.append({"index": e["paragraph"], "start": e["start"], "end": e["end"]})
    paragraphs[-1]["end"] = round(total, 3)
    return np.concatenate(pieces), entries, paragraphs, lesson


def run_lesson(project: Project, story: Any, client: TtsClient | None,
               log: Callable[[str], None]) -> None:
    sentences = [s for p in story.paragraphs for s in split_sentences(p)]
    if len(sentences) != 1 or not story.breakdown:
        raise StoryTooLongError(
            f"{story.id}：レッスン形式は、本文が1文で breakdown（かたまり）があるものだけです。"
        )
    voice = voices.resolve(project, story.voice or None)
    cfg = {k: float(project.get(f"lesson.{k}", d)) for k, d in (
        ("normal_speed", 1.0), ("slow_speed", 0.8), ("sentence_hold", 1.2),
        ("chunk_hold", 3.5), ("shadow_ratio", 1.3), ("next_seconds", 3.0))}
    settings = VoiceSettings(
        speaker_id=voice.style_id, sample_rate=int(project.get("tts.sample_rate", 48000)),
        pause_sentence=0.0, pause_paragraph=0.0,
        pre_silence=float(project.get("tts.pre_silence")), post_silence=0.0,
        intonation_scale=voice.intonation_scale,
    )
    if client is None:
        words = userdict.load(project.path(project.get("tts.user_dict")))
        client = voices.connect(voice, words, log)
    steps = lesson_steps(sentences[0], story.breakdown, cfg)
    log(f"{story.id}: 声 {voice.key}（{voice.credit}）, レッスン形式（かたまり {len(story.breakdown)} 個）")
    clips = [_synthesize(client, client.audio_query(tts_text(s.text), settings.speaker_id), s.speed, settings)
             for s in steps]
    audio, entries, paragraphs, lesson = assemble_lesson(
        steps, clips, settings.sample_rate, pre_silence=settings.pre_silence,
        shadow_ratio=cfg["shadow_ratio"], next_seconds=cfg["next_seconds"])
    duration = len(audio) / settings.sample_rate
    max_seconds = float(project.get("tts.max_voice_seconds"))
    if duration > max_seconds:
        raise StoryTooLongError(
            f"音声が {duration:.1f} 秒あり、上限 {max_seconds} 秒を超えています。"
            "かたまりを減らすか、lesson.chunk_hold を短くしてください。"
        )
    out = project.work_dir(story.id)
    sf.write(out / "voice.wav", audio, settings.sample_rate, subtype="PCM_16")
    timing = {
        "story_id": story.id, "voice": voice.key, "engine": voice.engine,
        "style_id": voice.style_id, "credit": voice.credit, "format": "lesson",
        "speed": cfg["slow_speed"], "intonation_scale": settings.intonation_scale,
        "sample_rate": settings.sample_rate, "duration": round(duration, 3),
        "paragraphs": paragraphs, "sentences": entries, "lesson": lesson,
    }
    (out / "timing.json").write_text(json.dumps(timing, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"→ {out / 'voice.wav'}（{duration:.2f} 秒）")
