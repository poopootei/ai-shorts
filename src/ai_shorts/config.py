"""config.yaml の読み込みとプロジェクト内のパス。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .errors import ConfigError

_MISSING = object()


def find_root(start: Path | None = None) -> Path:
    """config.example.yaml があるディレクトリをさかのぼって探す。AI_SHORTS_ROOT が優先。"""
    env = os.environ.get("AI_SHORTS_ROOT")
    if env:
        return Path(env).resolve()
    here = (start or Path.cwd()).resolve()
    for d in (here, *here.parents):
        if (d / "config.example.yaml").exists():
            return d
    raise ConfigError(
        "プロジェクトのルートが見つかりません。ai-shorts ディレクトリの中で実行してください。"
    )


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
        return p if p.is_absolute() else self.root / p

    def work_dir(self, story_id: str) -> Path:
        d = self.root / "work" / story_id
        d.mkdir(parents=True, exist_ok=True)
        return d


def load_project(root: Path | None = None) -> Project:
    root = root or find_root()
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
