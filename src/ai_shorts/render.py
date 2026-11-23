"""合成（render）: work/{id}/voice.wav (+ img_*.png, subs.ass, BGM) → work/{id}/video.mp4

画像は段落ごとに切り替え（クロスフェード）、なければ単色。subs.ass があれば焼き込む。
音声は numpy で 声 + BGM を混ぜ、pyloudnorm で目標の音量に揃えてから ffmpeg で動画と合わせる。
"""

from __future__ import annotations

import json
import os
import warnings
from pathlib import Path

import numpy as np
import pyloudnorm as pyln
import soundfile as sf

from . import ffmpeg
from .config import Project
from .errors import AiShortsError

MIX_SAMPLE_RATE = 48000


def log(msg: str) -> None:
    print(f"[render] {msg}")


def rel_to_root(project: Project, p: Path) -> str:
    """ffmpeg は root で実行し、パスは root からの相対で渡す（drawtext / subtitles の Windows パス対策）。
    channels/{name}/ から共通の assets を指すときは ../../assets/... になる。"""
    return Path(os.path.relpath(p, project.root)).as_posix()


# ---- 音声 ----------------------------------------------------------------

def to_stereo(x: np.ndarray) -> np.ndarray:
    return np.repeat(x[:, None], 2, axis=1) if x.ndim == 1 else x[:, :2]


def mix(voice: np.ndarray, bgm: np.ndarray | None, bgm_gain_db: float) -> np.ndarray:
    """声に BGM を一定の音量で重ねる。BGM は頭から使い、声の長さで切る（足りなければ無音）。"""
    voice = to_stereo(voice)
    if bgm is None:
        return voice.copy()
    bgm = to_stereo(bgm)[: len(voice)]
    if len(bgm) < len(voice):
        bgm = np.pad(bgm, ((0, len(voice) - len(bgm)), (0, 0)))
    return voice + bgm * (10.0 ** (bgm_gain_db / 20.0))


def normalize_loudness(x: np.ndarray, sample_rate: int, target_lufs: float) -> np.ndarray:
    meter = pyln.Meter(sample_rate)
    current = meter.integrated_loudness(x)
    if not np.isfinite(current):
        raise AiShortsError("音声が無音のため音量を測れません。voice.wav を確認してください。")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # クリップの警告は soft_limit で処理する
        return pyln.normalize.loudness(x, current, target_lufs)


def soft_limit(x: np.ndarray, knee: float, ceiling: float) -> np.ndarray:
    """|x| が knee を超えた部分だけを tanh でなだらかに ceiling 未満へ押さえる。"""
    a = np.abs(x)
    over = a > knee
    if not over.any():
        return x
    y = x.copy()
    room = ceiling - knee
    y[over] = np.sign(x[over]) * (knee + room * np.tanh((a[over] - knee) / room))
    return y


def load_bgm(project: Project, work: Path) -> np.ndarray | None:
    rel = project.get("bgm.path", None)
    if not rel:
        log("BGM の設定がないので、声だけで作ります。")
        return None
    src = project.path(rel)
    if not src.exists():
        log(f"BGM が見つからないので、声だけで作ります: {src}")
        return None
    converted = work / "bgm_48k.wav"
    ffmpeg.convert_audio(src, converted, MIX_SAMPLE_RATE, 2)
    data, _ = sf.read(converted, dtype="float32", always_2d=True)
    start = int(float(project.get("bgm.start_seconds", 0)) * MIX_SAMPLE_RATE)
    return data[start:]


def build_audio(project: Project, work: Path) -> tuple[Path, float]:
    voice_path = work / "voice.wav"
    if not voice_path.exists():
        raise AiShortsError(f"{voice_path} がありません。先に tts を実行してください。")
    voice, sr = sf.read(voice_path, dtype="float32")
    if sr != MIX_SAMPLE_RATE:
        converted = work / "voice_48k.wav"
        ffmpeg.convert_audio(voice_path, converted, MIX_SAMPLE_RATE, 1)
        voice, _ = sf.read(converted, dtype="float32")

    mixed = mix(voice, load_bgm(project, work), float(project.get("bgm.gain_db")))
    target = float(project.get("render.target_lufs"))
    out = normalize_loudness(mixed, MIX_SAMPLE_RATE, target)
    out = soft_limit(
        out,
        knee=float(project.get("render.limiter_knee", 0.85)),
        ceiling=float(project.get("render.limiter_ceiling", 0.98)),
    )
    path = work / "mix.wav"
    sf.write(path, out, MIX_SAMPLE_RATE, subtype="PCM_24")
    measured = pyln.Meter(MIX_SAMPLE_RATE).integrated_loudness(out)
    log(f"音声: {len(out) / MIX_SAMPLE_RATE:.2f} 秒, {measured:.1f} LUFS（目標 {target}）")
    return path, len(out) / MIX_SAMPLE_RATE


# ---- 映像 ----------------------------------------------------------------

def segment_durations(boundaries: list[float], duration: float, crossfade: float) -> list[float]:
    """画像 i を boundaries の間に表示する。切り替えを境目の前後 crossfade/2 秒にまたがらせるため、
    各画像の長さを足し出す。xfade でつなぐと合計がちょうど duration になる。"""
    edges = [0.0, *boundaries, duration]
    n = len(edges) - 1
    if n == 1:
        return [duration]
    out = []
    for i in range(n):
        d = edges[i + 1] - edges[i]
        d += crossfade if 0 < i < n - 1 else crossfade / 2
        out.append(round(d, 3))
    return out


def image_boundaries(timing: dict, n_images: int, duration: float) -> list[float]:
    """画像を切り替える時刻。画像の数と段落の数が同じなら、段落の間の無音の真ん中で切り替える。"""
    paras = timing.get("paragraphs", [])
    if n_images == len(paras):
        return [round((paras[i]["end"] + paras[i + 1]["start"]) / 2, 3) for i in range(n_images - 1)]
    log(f"画像 {n_images} 枚と段落 {len(paras)} 個の数が合わないので、等分で切り替えます。")
    return [round(duration * i / n_images, 3) for i in range(1, n_images)]


def clip_filter(index: int, *, width: int, height: int, seconds: float, zoom_end: float,
                zoom: bool) -> str:
    """画像を画面いっぱいに切り抜き、その画像の表示時間で 1.0 → zoom_end へゆっくり拡大する。"""
    steps = [f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=increase",
             f"crop={width}:{height}"]
    if zoom and zoom_end > 1.0:
        grow = zoom_end - 1.0
        steps += [
            f"scale=w='trunc({width}*(1+{grow}*t/{seconds:.3f})/2)*2':h=-2"
            ":eval=frame:flags=bicubic",
            f"crop={width}:{height}",
        ]
    steps += ["setsar=1", "format=yuv420p", f"[c{index}]"]
    return ",".join(steps[:-1]) + steps[-1]


def video_filter(
    *, width: int, height: int, durations: list[float], crossfade: float, zoom_end: float,
    has_images: bool, subs: str | None, credit: str | None,
) -> str:
    parts = [clip_filter(i, width=width, height=height, seconds=d, zoom_end=zoom_end,
                         zoom=has_images) for i, d in enumerate(durations)]
    last = "c0"
    offset = 0.0
    for i in range(1, len(durations)):
        offset += durations[i - 1] - crossfade
        parts.append(f"[{last}][c{i}]xfade=transition=fade:duration={crossfade}"
                     f":offset={offset:.3f}[x{i}]")
        last = f"x{i}"
    tail = [s for s in (subs, credit) if s]
    parts.append(f"[{last}]" + ",".join([*tail, "format=yuv420p"]) + "[v]")
    return ";".join(parts)


def credit_filter(project: Project, work: Path) -> str | None:
    """VOICEVOX のクレジットを左上に小さく出す。パスは ffmpeg を root で実行して相対で渡す。"""
    if not project.get("render.show_credit_overlay", True):
        return None
    font = project.path(project.get("subs.font_file"))
    if not font.exists():
        log(f"フォントがないので、クレジット表示を省きます: {font}")
        return None
    credit = json.loads((work / "timing.json").read_text(encoding="utf-8")).get("credit", "")
    if not credit:
        log("timing.json にクレジットがないので、表示を省きます（tts を実行し直してください）。")
        return None
    text_file = work / "credit.txt"
    text_file.write_text(credit, encoding="utf-8")
    rel_text = rel_to_root(project, text_file)
    rel_font = rel_to_root(project, font)
    size = int(project.get("render.credit_font_size", 28))
    margin = int(project.get("render.credit_margin", 40))
    y_ratio = float(project.get("render.credit_y_ratio", 0.06))
    return (
        f"drawtext=textfile={rel_text}:fontfile={rel_font}:fontsize={size}"
        f":fontcolor=white@0.75:borderw=2:bordercolor=black@0.6"
        f":x={margin}:y=h*{y_ratio}"
    )


def subs_filter(project: Project, work: Path) -> str | None:
    ass = work / "subs.ass"
    if not ass.exists():
        log("subs.ass がないので、字幕なしで作ります。")
        return None
    font = project.path(project.get("subs.font_file"))
    rel_ass = rel_to_root(project, ass)
    rel_fonts = rel_to_root(project, font.parent)
    return f"subtitles=filename={rel_ass}:fontsdir={rel_fonts}"


def find_images(work: Path) -> list[Path]:
    images = []
    while (p := work / f"img_{len(images) + 1}.png").exists():
        images.append(p)
    return images


def run(project: Project, story_id: str) -> None:
    work = project.root / "work" / story_id  # tts が作る。なければ build_audio が止める
    audio_path, duration = build_audio(project, work)

    width = int(project.get("render.width"))
    height = int(project.get("render.height"))
    fps = int(project.get("render.fps"))
    crossfade = float(project.get("render.crossfade_seconds"))
    max_seconds = float(project.get("render.max_video_seconds"))
    if duration > max_seconds:
        raise AiShortsError(
            f"音声が {duration:.2f} 秒で、上限 {max_seconds} 秒を超えています。tts を見直してください。"
        )

    def rel(p: Path) -> str:
        return rel_to_root(project, p)

    images = find_images(work)
    if images:
        timing = json.loads((work / "timing.json").read_text(encoding="utf-8"))
        durations = segment_durations(image_boundaries(timing, len(images), duration),
                                      duration, crossfade)
        inputs = []
        for img, d in zip(images, durations):
            inputs += ["-loop", "1", "-framerate", str(fps), "-t", f"{d:.3f}", "-i", rel(img)]
    else:
        color = project.get("render.background_color", "0x14141c")
        log("img_1.png がないので、単色の背景で作ります。")
        durations = [duration]
        inputs = ["-f", "lavfi", "-i", f"color=c={color}:s={width}x{height}:r={fps}:d={duration:.3f}"]

    vf = video_filter(
        width=width, height=height, durations=durations, crossfade=crossfade,
        zoom_end=float(project.get("render.zoom_end")), has_images=bool(images),
        subs=subs_filter(project, work), credit=credit_filter(project, work),
    )
    out = work / "video.mp4"
    audio_index = len(durations)
    ffmpeg.run(
        [
            *inputs,
            "-i", rel(audio_path),
            "-filter_complex", vf,
            "-map", "[v]", "-map", f"{audio_index}:a",
            "-t", f"{duration:.3f}",
            "-r", str(fps),
            "-c:v", "libx264",
            "-preset", str(project.get("render.x264_preset", "medium")),
            "-crf", str(project.get("render.crf", 20)),
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", str(MIX_SAMPLE_RATE),
            "-movflags", "+faststart",
            rel(out),
        ],
        cwd=project.root,
    )
    actual = ffmpeg.duration(out)
    (work / "render.json").write_text(
        json.dumps({"duration": round(actual, 3), "images": [p.name for p in images],
                    "image_seconds": durations}, indent=2),
        encoding="utf-8",
    )
    log(f"→ {out}（{actual:.2f} 秒, 画像 {len(images)} 枚）")
