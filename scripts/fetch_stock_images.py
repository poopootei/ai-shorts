"""ComfyUI ができるまでの仮の背景：Openverse から CC0 / パブリックドメインの写真を取ってくる。

    python scripts/fetch_stock_images.py --id sample-001 \
        --query "vending machine night" --query "coffee can" --query "dark doorway"

段落ごとに --query を1つ（段落の数と同じだけ）指定する。
検索結果の順番は毎回変わるので、決めた画像は --query "id:<Openverse の ID>" で指定すると確実。
ID は images.json の openverse_id、または検索結果の id。
work/{id}/img_1.png .. img_N.png（1080x1920 に切り抜き）と、出典・ライセンスを images.json に書く。
CC0 / PDM だけを使うので、商用利用でき、クレジット表記は不要（ただし出典は記録しておく）。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

API = "https://api.openverse.org/v1/images/"
HEADERS = {"User-Agent": "ai-shorts/0.1 (local video pipeline)"}
ALLOWED_LICENSES = {"cc0", "pdm"}


def api_get(url: str, params: dict | None = None, attempts: int = 6) -> dict:
    """Openverse は混むと 504 を返すので、間をあけてやり直す。"""
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=30)
            if resp.status_code < 500:
                resp.raise_for_status()
                return resp.json()
        except (requests.ConnectionError, requests.Timeout):
            if attempt == attempts:
                raise
        if attempt < attempts:
            time.sleep(3 * attempt)
    resp.raise_for_status()
    return {}


def search(query: str, page_size: int = 20) -> list[dict]:
    params = {"q": query, "license": ",".join(sorted(ALLOWED_LICENSES)),
              "page_size": page_size, "mature": "false"}
    return api_get(API, params).get("results", [])


def score(r: dict) -> float:
    """縦長で、解像度が高いものを優先する。"""
    w, h = r.get("width") or 0, r.get("height") or 0
    if not w or not h or h < 900:
        return -1
    portrait = 1.5 if h >= w else 1.0
    return portrait * min(h, 4000)


def get_by_id(image_id: str) -> dict:
    r = api_get(f"{API}{image_id}/")
    if r.get("license") not in ALLOWED_LICENSES:
        sys.exit(f"{image_id} のライセンスは {r.get('license')} です（CC0 / PDM だけ使えます）。")
    return r


def pick(query: str, used: set[str], skip: int) -> dict:
    """query が "id:<Openverse の ID>" なら、その画像を使う（検索結果の順番は毎回変わるため）。"""
    if query.startswith("id:"):
        return get_by_id(query[3:])
    results = [r for r in search(query)
               if r.get("license") in ALLOWED_LICENSES and r["id"] not in used and score(r) > 0]
    results.sort(key=score, reverse=True)
    if len(results) <= skip:
        sys.exit(f"「{query}」で使える画像が見つかりません。別の言葉で試してください。")
    return results[skip]


def download(url: str, dst: Path) -> None:
    with requests.get(url, headers=HEADERS, timeout=60, stream=True) as resp:
        resp.raise_for_status()
        ctype = resp.headers.get("Content-Type", "")
        if not ctype.startswith("image/"):
            sys.exit(f"画像ではないものが返りました（{ctype}）: {url}")
        with dst.open("wb") as f:
            for chunk in resp.iter_content(1 << 16):
                f.write(chunk)


def to_portrait_png(src: Path, dst: Path, width: int, height: int) -> None:
    vf = (f"scale={width}:{height}:force_original_aspect_ratio=increase,"
          f"crop={width}:{height},setsar=1")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(src), "-vf", vf, "-frames:v", "1", str(dst)], check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id", required=True)
    ap.add_argument("--query", action="append", required=True, help="段落ごとの検索語（英語）")
    ap.add_argument("--skip", type=int, action="append",
                    help="段落ごとに、上位から何枚飛ばすか（気に入らないとき差し替える）")
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--height", type=int, default=1920)
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    work = root / "work" / args.id
    work.mkdir(parents=True, exist_ok=True)
    skips = args.skip or [0] * len(args.query)
    if len(skips) != len(args.query):
        sys.exit("--skip は --query と同じ数だけ指定してください。")

    records, used = [], set()
    with tempfile.TemporaryDirectory(prefix="ai_shorts_dl_") as tmp:
        for i, (query, skip) in enumerate(zip(args.query, skips), start=1):
            r = pick(query, used, skip)
            used.add(r["id"])
            raw = Path(tmp) / f"raw_{i}"
            download(r["url"], raw)
            dst = work / f"img_{i}.png"
            to_portrait_png(raw, dst, args.width, args.height)
            records.append({
                "file": dst.name, "query": query, "openverse_id": r["id"],
                "title": r.get("title"), "creator": r.get("creator"),
                "license": r["license"], "license_url": r.get("license_url"),
                "source": r.get("source"), "landing_url": r.get("foreign_landing_url"),
                "image_url": r["url"], "original_size": [r.get("width"), r.get("height")],
            })
            print(f"img_{i}.png ← {r['license']} {r.get('source')}: {r.get('title')!r}")

    (work / "images.json").write_text(
        json.dumps({"source": "openverse", "images": records}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
