"""ffmpeg / ffprobe の薄いラッパー。"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .errors import ExternalToolError


def find(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise ExternalToolError(
            f"{name} が見つかりません。ffmpeg（libass つきのビルド）をインストールし、PATH を通してください。"
        )
    return path


def run(args: list[str], cwd: Path | None = None) -> None:
    cmd = [find("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", *args]
    proc = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-15:])
        raise ExternalToolError(f"ffmpeg が失敗しました（終了コード {proc.returncode}）:\n{tail}")


def probe(path: Path) -> dict:
    cmd = [
        find("ffprobe"), "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if proc.returncode != 0:
        raise ExternalToolError(f"ffprobe が {path} を読めません: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def duration(path: Path) -> float:
    return float(probe(path)["format"]["duration"])


def convert_audio(src: Path, dst: Path, sample_rate: int, channels: int) -> None:
    run(["-i", str(src), "-ar", str(sample_rate), "-ac", str(channels),
         "-c:a", "pcm_f32le", str(dst)])
