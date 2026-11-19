"""背景の候補を並べたシートを作る（1行 = 1検索語、上位4枚）。Openverse の CC0 / PDM だけ。

    python scripts/preview_backgrounds.py --name 20261120-001 "radio telescope night" "nebula" "milky way"

シートは work/_previews/<name>_sheet.png。端末には「検索語 [列] ID ライセンス 出典: タイトル」を出す。
選んだ画像は ID で取ってくる（検索結果の順番は毎回変わるので、--skip ではなく ID を使う）:

    python scripts/fetch_stock_images.py --id 20261120-001 --query "id:<ID1>" --query "id:<ID2>" --query "id:<ID3>"

灰色のマスはサムネイルを取れなかったもの、黒のマスは候補が4枚に満たなかったもの。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_stock_images import HEADERS, score, search  # noqa: E402

TILE_W, TILE_H = 180, 320


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "quiet", "-y", *args], check=True)


def blank(path: Path, color: str) -> None:
    ffmpeg("-f", "lavfi", "-i", f"color=c={color}:s={TILE_W}x{TILE_H}", "-frames:v", "1", str(path))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("queries", nargs="+", help="検索語（英語）")
    ap.add_argument("--name", required=True, help="シートの名前（物語の id など）")
    ap.add_argument("--per-query", type=int, default=4)
    args = ap.parse_args()

    out = ROOT / "work" / "_previews"
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    with tempfile.TemporaryDirectory(prefix="ai_shorts_prev_") as tmp:
        tmp = Path(tmp)
        for qi, q in enumerate(args.queries):
            rs = sorted([r for r in search(q) if score(r) > 0], key=score, reverse=True)[: args.per_query]
            tiles = []
            for i, r in enumerate(rs):
                raw, tile = tmp / f"{qi}_{i}", tmp / f"{qi}_{i}.png"
                try:
                    raw.write_bytes(requests.get(r.get("thumbnail") or r["url"], headers=HEADERS, timeout=30).content)
                    ffmpeg("-i", str(raw), "-vf",
                           f"scale={TILE_W}:{TILE_H}:force_original_aspect_ratio=increase,crop={TILE_W}:{TILE_H}",
                           "-frames:v", "1", str(tile))
                except Exception:
                    blank(tile, "gray")
                tiles.append(tile)
                print(f"{q} [{i}] {r['id']} {r['license']} {r['source']}: {r.get('title')}")
            if not rs:
                print(f"{q}: 候補なし（別の言葉で試す）")
            while len(tiles) < args.per_query:
                t = tmp / f"{qi}_pad{len(tiles)}.png"
                blank(t, "black")
                tiles.append(t)
            row = tmp / f"row{qi}.png"
            ffmpeg(*sum([["-i", str(t)] for t in tiles], []), "-filter_complex", f"hstack={len(tiles)}", str(row))
            rows.append(row)
        sheet = out / f"{args.name}_sheet.png"
        if len(rows) == 1:
            ffmpeg("-i", str(rows[0]), str(sheet))
        else:
            ffmpeg(*sum([["-i", str(r)] for r in rows], []), "-filter_complex", f"vstack={len(rows)}", str(sheet))
    print(f"sheet: {sheet}")


if __name__ == "__main__":
    main()
