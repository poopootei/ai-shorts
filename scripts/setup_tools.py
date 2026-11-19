"""音声合成エンジンと声を tools/ に入れる（環境の作り直し・声の追加用）。

    python scripts/setup_tools.py coeiroink                     # COEIROINK v2.13.0 CPU 版（約 592MB）
    python scripts/setup_tools.py aivisspeech                   # AivisSpeech Engine 1.2.0（約 217MB）
    python scripts/setup_tools.py coeiroink-voices              # 公式キャラの一覧（UUID・サイズ・スタイル）※エンジン起動中
    python scripts/setup_tools.py coeiroink-voice <UUID>        # 公式キャラを追加（0.35〜1.4GB）※エンジン起動中
    python scripts/setup_tools.py aivis-model <AIVM の UUID>    # AivisHub のモデルを追加（約 250MB）※エンジン起動中

ダウンロードは大きいので、実行する前に必ずユーザーに大きさを伝えて了承を得る（CLAUDE.md・runbook）。
- 7z は Windows 標準の tar（C:/Windows/System32/tar.exe、libarchive）で展開する。7-Zip は入れない。
- 展開前に中身のパスを確かめ、絶対パスや .. を含むものがあれば止める。
- 圧縮ファイルは tools/_download/ に落とし、展開できたら消す。
- AivisSpeech は SHA-256 を GitHub の値と照合する。COEIROINK は公開値がないので、記録用に表示だけする。
- AivisSpeech は初回起動時に既定モデルと BERT（約 900MB）を %APPDATA%/AivisSpeech-Engine に自動で落とす。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

import requests

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
DOWNLOAD = TOOLS / "_download"
TAR = "C:/Windows/System32/tar.exe"
UA = {"User-Agent": "ai-shorts/0.1 (local setup)"}

# 版を上げるときはここを書き換える（URL は https://coeiroink.com/download のページのスクリプト内にある）
COEIROINK_VERSION = "2.13.0"
COEIROINK_URL = ("https://www.dropbox.com/scl/fi/ytyqfqmwt47esd7o74zmf/COEIROINK_WIN_CPU_v.2.13.0.zip"
                 "?rlkey=7omtulugom9d0mho2bw8qzpjr&st=6ao2m6va&dl=1")
AIVIS_VERSION = "1.2.0"
AIVIS_REPO = "Aivis-Project/AivisSpeech-Engine"
COEIROINK_API = "http://127.0.0.1:50032"
AIVIS_API = "http://127.0.0.1:10101"


def download(url: str, dst: Path) -> str:
    dst.parent.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    with requests.get(url, headers=UA, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        with dst.open("wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  {done / 1e6:7.1f} / {total / 1e6:.1f} MB", end="", flush=True)
    print()
    return h.hexdigest()


def safe_names(names: list[str]) -> None:
    bad = [n for n in names if n.startswith(("/", "\\")) or ":" in n
           or ".." in PurePosixPath(n.replace("\\", "/")).parts]
    if bad:
        sys.exit(f"危ないパスが入っているので止めます: {bad[:3]}")


def extract_7z(archive: Path, dest: Path, strip: int) -> None:
    names = subprocess.run([TAR, "-tf", str(archive)], capture_output=True, text=True, check=True).stdout.split("\n")
    safe_names([n for n in names if n])
    dest.mkdir(parents=True)
    subprocess.run([TAR, "-xf", str(archive), "-C", str(dest), "--strip-components", str(strip)], check=True)


def need_absent(path: Path) -> None:
    if path.exists():
        sys.exit(f"{path} はもうあります。入れ直すときは、エンジンを止めてからフォルダを消してください。")


def setup_coeiroink() -> None:
    dest = TOOLS / "coeiroink"
    need_absent(dest)
    z = DOWNLOAD / f"COEIROINK_WIN_CPU_v.{COEIROINK_VERSION}.zip"
    print(f"COEIROINK {COEIROINK_VERSION} をダウンロード")
    print("  sha256:", download(COEIROINK_URL, z), "（公開値なし。記録用）")
    with zipfile.ZipFile(z) as zf:
        safe_names(zf.namelist())
        inner = [n for n in zf.namelist() if n.endswith(".7z.001")]
        if len(inner) != 1:
            sys.exit(f"zip の中に .7z.001 が1つではありません: {zf.namelist()}")
        zf.extract(inner[0], DOWNLOAD)  # 同梱の .exe は使わない
    extract_7z(DOWNLOAD / inner[0], dest, strip=1)
    shutil.rmtree(DOWNLOAD)
    print(f"→ {dest}（同梱の声: つくよみちゃん）")


def setup_aivisspeech() -> None:
    dest = TOOLS / "aivisspeech_engine"
    need_absent(dest)
    rel = requests.get(f"https://api.github.com/repos/{AIVIS_REPO}/releases/tags/{AIVIS_VERSION}",
                       headers=UA, timeout=30).json()
    asset = next(a for a in rel["assets"] if a["name"].startswith("AivisSpeech-Engine-Windows-x64")
                 and a["name"].endswith(".7z.001"))
    print(f"AivisSpeech Engine {AIVIS_VERSION}: {asset['name']}（{asset['size'] / 1e6:.0f} MB）")
    archive = DOWNLOAD / "aivis.7z"
    digest = download(asset["browser_download_url"], archive)
    expected = (asset.get("digest") or "").removeprefix("sha256:")
    if expected and digest != expected:
        sys.exit(f"SHA-256 が一致しません（{digest} != {expected}）。展開しません。")
    print("  sha256 一致" if expected else "  sha256（公開値なし）: " + digest)
    extract_7z(archive, dest, strip=1)
    shutil.rmtree(DOWNLOAD)
    print(f"→ {dest}。起動は scripts/start_tts.ps1（--disable_sentry つき）")


def coeiroink_info() -> list[dict]:
    try:
        return requests.get(f"{COEIROINK_API}/v1/download_info", timeout=60).json()
    except requests.RequestException:
        sys.exit("COEIROINK エンジンが動いていません（scripts/start_tts.ps1）。")


def installed_coeiroink_voices() -> set[str]:
    """speaker_info/ の各フォルダの metas.json にある speakerUuid（フォルダ名は UUID とは限らない）。"""
    have = set()
    for p in (TOOLS / "coeiroink" / "speaker_info").glob("*/metas.json"):
        have.add(json.loads(p.read_text(encoding="utf-8")).get("speakerUuid", p.parent.name))
    return have


def list_coeiroink_voices() -> None:
    have = installed_coeiroink_voices()
    for i in coeiroink_info():
        s = i["speaker"]
        mark = "入っている" if s["speaker_uuid"] in have else ""
        styles = ", ".join(f"{st['name']}({st['id']})" for st in s["styles"])
        print(f"{s['name']:14s} {s['speaker_uuid']} {i['volume']:>8s} {mark:6s} {styles}")


def add_coeiroink_voice(uuid: str) -> None:
    info = next((i for i in coeiroink_info() if i["speaker"]["speaker_uuid"] == uuid), None)
    if not info:
        sys.exit(f"{uuid} は公式キャラの一覧にありません（coeiroink-voices で確認）。")
    dest = TOOLS / "coeiroink" / "speaker_info"
    if uuid in installed_coeiroink_voices():
        sys.exit(f"{info['speaker']['name']} はもう入っています。")
    z = DOWNLOAD / f"{uuid}.zip"
    print(f"{info['speaker']['name']}（{info['volume']}）をダウンロード")
    download(info["download_path"], z)
    with zipfile.ZipFile(z) as zf:
        safe_names(zf.namelist())
        zf.extractall(dest)
    shutil.rmtree(DOWNLOAD)
    print(f"→ {dest / uuid}")
    print("COEIROINK エンジンを再起動してください（起動時に読んだ声しか使えない）。")
    print(f"規約: https://coeiroink.com/character/audio-character/ の該当キャラのページで、商用利用とクレジット表記を確認する。")


def add_aivis_model(uuid: str) -> None:
    url = f"https://api.aivis-project.com/v1/aivm-models/{uuid}/download?model_type=AIVMX"
    try:
        r = requests.post(f"{AIVIS_API}/aivm_models/install", data={"url": url}, timeout=900)
    except requests.RequestException:
        sys.exit("AivisSpeech エンジンが動いていません（scripts/start_tts.ps1）。")
    r.raise_for_status()
    m = requests.get(f"{AIVIS_API}/aivm_models/{uuid}", timeout=30).json()
    man = m["manifest"]
    print(f"→ {man['name']} を入れました")
    lic = (man.get("license") or "").strip()
    print("ライセンス:", lic.splitlines()[0] if lic else "（記載なし。使わないこと）")
    for line in lic.splitlines():
        if any(k in line for k in ("営利", "商用", "クレジット")):
            print("  ", line.strip()[:120])
    for sp in requests.get(f"{AIVIS_API}/speakers", timeout=30).json():
        if sp["speaker_uuid"] in {s["uuid"] for s in man.get("speakers", [])} or sp["name"] == man["name"]:
            print("スタイル ID:", [(st["name"], st["id"]) for st in sp["styles"]])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("coeiroink")
    sub.add_parser("aivisspeech")
    sub.add_parser("coeiroink-voices")
    sub.add_parser("coeiroink-voice").add_argument("uuid")
    sub.add_parser("aivis-model").add_argument("uuid")
    args = ap.parse_args()
    {
        "coeiroink": setup_coeiroink,
        "aivisspeech": setup_aivisspeech,
        "coeiroink-voices": list_coeiroink_voices,
        "coeiroink-voice": lambda: add_coeiroink_voice(args.uuid),
        "aivis-model": lambda: add_aivis_model(args.uuid),
    }[args.cmd]()


if __name__ == "__main__":
    main()
