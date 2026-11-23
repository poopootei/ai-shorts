"""音声合成エンジンが動いているか、config の声がエンジンに入っているかを確かめる。

    python scripts/tts_status.py --channel shortshort

止まっているエンジンは scripts/start_tts.ps1 で起動する（COEIROINK と AivisSpeech）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ai_shorts.config import load_project, script_root  # noqa: E402


def styles(engine_type: str, url: str) -> dict[int, str] | None:
    try:
        if engine_type == "coeiroink":
            data = requests.get(f"{url}/v1/speakers", timeout=5).json()
            return {st["styleId"]: f"{sp['speakerName']} {st['styleName']}" for sp in data for st in sp["styles"]}
        data = requests.get(f"{url}/speakers", timeout=5).json()
        return {st["id"]: f"{sp['name']} {st['name']}" for sp in data for st in sp["styles"]}
    except requests.RequestException:
        return None


def main() -> None:
    project = load_project(script_root())
    engines = project.get("engines")
    found = {name: styles(e["type"], e["url"]) for name, e in engines.items()}
    for name, e in engines.items():
        print(f"{name:12s} {e['url']:28s} {'動いている' if found[name] is not None else '止まっている'}")
    print()
    bad = 0
    default = project.get("tts.default_voice")
    for key, v in project.get("voices").items():
        st = found.get(v["engine"])
        if st is None:
            state = "エンジン停止中"
            bad += 1
        elif int(v["style_id"]) in st:
            state = f"OK（{st[int(v['style_id'])]}）"
        else:
            state = "NG: エンジンにこのスタイル ID がない（声の追加か再起動が必要）"
            bad += 1
        mark = "*" if key == default else " "
        print(f"{mark} {key:18s} {v['engine']:12s} {v['style_id']:>11} {state}")
    print("\n* = tts.default_voice")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
