"""config.yaml の読み込みとプロジェクト内のパス。"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .errors import ConfigError

_MISSING = object()


REPO = Path(__file__).resolve().parents[2]
CHANNELS = REPO / "channels"


def channel_names() -> list[str]:
    """channels/ の下のチャンネル（config.example.yaml があるもの）。"""
    if not CHANNELS.is_dir():
        return []
    return sorted(d.name for d in CHANNELS.iterdir() if (d / "config.example.yaml").exists())


def channel_root(name: str) -> Path:
    d = CHANNELS / name
    if not (d / "config.example.yaml").exists():
        raise ConfigError(f"チャンネル {name} がありません（あるもの: {' / '.join(channel_names())}）。")
    return d.resolve()


def find_root(start: Path | None = None, channel: str | None = None) -> Path:
    """チャンネルのフォルダ（channels/{name}/）を決める。

    優先順：引数の channel（--channel）→ AI_SHORTS_ROOT → AI_SHORTS_CHANNEL
    → 今いるフォルダから config.example.yaml をさかのぼって探す。
    """
    if channel:
        return channel_root(channel)
    env = os.environ.get("AI_SHORTS_ROOT")
    if env:
        return Path(env).resolve()
    if os.environ.get("AI_SHORTS_CHANNEL"):
        return channel_root(os.environ["AI_SHORTS_CHANNEL"])
    here = (start or Path.cwd()).resolve()
    for d in (here, *here.parents):
        if (d / "config.example.yaml").exists():
            return d
    raise ConfigError(
        f"チャンネルを --channel で選んでください（{' / '.join(channel_names()) or 'channels/ が空'}）。"
    )


def script_root(argv: list[str] | None = None) -> Path:
    """scripts/ 用：コマンドラインの --channel（-c）からチャンネルのフォルダを決める。"""
    import argparse

    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("-c", "--channel")
    known, _ = ap.parse_known_args(sys.argv[1:] if argv is None else argv)
    try:
        return find_root(channel=known.channel)
    except ConfigError as e:
        raise SystemExit(f"エラー: {e}") from e


def add_channel_arg(ap) -> None:
    """scripts/ の argparse に --channel を足す（値は script_root が先に読む）。"""
    ap.add_argument("-c", "--channel", help=f"チャンネル（{' / '.join(channel_names())}）")


@dataclass(frozen=True)
class Project:
    root: Path
    config: dict[str, Any]

    def get(self, key: str, default: Any = _MISSING) -> Any:
        """'voicevox.speaker_id' のようなドット区切りで設定値を読む。"""
        node: Any = self.config
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                if default is _MISSING:
                    raise ConfigError(f"config.yaml に {key} がありません。")
                return default
            node = node[part]
        return node

    def path(self, rel: str | Path) -> Path:
        p = Path(rel)
        # channels/{name}/ から共通の assets を ../../assets/... で指せるように、.. を解決する
        return p if p.is_absolute() else (self.root / p).resolve()

    def work_dir(self, story_id: str) -> Path:
        d = self.root / "work" / story_id
        d.mkdir(parents=True, exist_ok=True)
        return d


def load_project(root: Path | None = None, channel: str | None = None) -> Project:
    root = root or find_root(channel=channel)
    cfg_path = root / "config.yaml"
    if not cfg_path.exists():
        raise ConfigError(
            f"{cfg_path} がありません。config.example.yaml をコピーして作ってください。"
        )
    with cfg_path.open(encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    if not isinstance(config, dict):
        raise ConfigError("config.yaml の形式が正しくありません。")
    return Project(root=root, config=config)
