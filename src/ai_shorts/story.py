"""物語 JSON の読み込みと、段落・文への分割。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .config import Project
from .errors import StoryError

_TERMINATORS = "。！？!?"
_OPEN = "「『（(【"
_CLOSE = "」』）)】"


@dataclass
class Story:
    id: str
    title: str
    hook: str
    body: str
    image_prompts: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    approved: bool = False
    notes: str = ""
    voice: str = ""  # config.yaml の voices のキー。空なら tts.default_voice
    source: str = ""  # 出典（青空文庫の作品など）。あれば説明文に「出典：」で出す
    # 学習者向け（subs.mode: learner）：文ごとの英訳。本文の文と同じ数・同じ順
    translations: list[str] = field(default_factory=list)
    # レッスン形式（format: lesson）：本文の1文を分けたかたまり [{"ja": ルビ付き, "en": 意味, "note": 文法のメモ}]
    breakdown: list[dict] = field(default_factory=list)
    next: str = ""   # 最後に出す「次の1文」の予告（英語）。about があればそちらを出す
    about: str = ""  # 最後に出す、作品の出典と背景の一文（英語）。見出しは About this story
    # 映像：空か "images" = 静止画の背景（いつもの流れ）、"3d" = 3D の舞台（scripts/blender/{id}.py。D-028）
    visual: str = ""

    @property
    def is_3d(self) -> bool:
        return self.visual == "3d"

    @property
    def paragraphs(self) -> list[str]:
        return split_paragraphs(self.body)


def split_paragraphs(body: str) -> list[str]:
    return [p.strip() for p in body.splitlines() if p.strip()]


def split_sentences(text: str) -> list[str]:
    """句点・感嘆符・疑問符で区切る。かぎかっこの中では区切らない。"""
    sentences: list[str] = []
    buf = ""
    depth = 0
    i = 0
    while i < len(text):
        ch = text[i]
        buf += ch
        i += 1
        if ch in _OPEN:
            depth += 1
        elif ch in _CLOSE:
            depth = max(0, depth - 1)
        elif ch in _TERMINATORS and depth == 0:
            # 「！？」や「。」」のような続きの記号は同じ文に含める
            while i < len(text) and text[i] in _TERMINATORS:
                buf += text[i]
                i += 1
            if buf.strip():
                sentences.append(buf.strip())
            buf = ""
    if buf.strip():
        sentences.append(buf.strip())
    return sentences


def load_approved(project: Project, story_id: str) -> Story:
    path = project.root / "stories" / "approved" / f"{story_id}.json"
    if not path.exists():
        raise StoryError(f"承認済みの物語が見つかりません: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise StoryError(f"{path} の JSON が読めません: {e}") from e
    if data.get("approved") is not True:
        raise StoryError(f"{story_id} は approved: true になっていません。")
    if data.get("id") != story_id:
        raise StoryError(f"{path} の id が {data.get('id')!r} で、ファイル名と一致しません。")
    known = Story.__dataclass_fields__.keys()
    try:
        return Story(**{k: v for k, v in data.items() if k in known})
    except TypeError as e:
        raise StoryError(f"{path} に必要な項目がありません: {e}") from e


VISUALS = ("", "images", "3d")


def is_3d_story(project: Project, story_id: str) -> bool:
    """承認済みの物語が 3D で作るものか（JSON の visual。読めなければ False）。"""
    path = project.root / "stories" / "approved" / f"{story_id}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("visual") == "3d"
    except (OSError, json.JSONDecodeError):
        return False


def list_approved(project: Project) -> list[str]:
    d = project.root / "stories" / "approved"
    return sorted(p.stem for p in d.glob("*.json"))
