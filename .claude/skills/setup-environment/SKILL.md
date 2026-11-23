---
name: setup-environment
description: ai-shorts の作業環境（Python の .venv、ffmpeg、音声合成エンジン COEIROINK / AivisSpeech、声、設定）を新しく作る・作り直す・壊れていないか確かめる。「環境を作って」「別の PC で」「セットアップ」「エンジンを入れ直したい」「tools が消えた」「pytest が動かない」「モジュールが見つからない」など、環境づくりや復旧の依頼では必ずこのスキルを使う。
---

# 環境を作る・確かめる

`<ch>` はチャンネル名（CLAUDE.md の「チャンネル」）。`stories/`・`work/`・`upload/`・`config.yaml` などのパスは、チャンネルのフォルダ `channels/<ch>/` から見たもの。

表と大きさは `docs/runbook.md` の 1。作業のルートは `D:\prj\ai-shorts`。

## 確かめる（壊れていないか）

```bash
.venv/Scripts/python -m pytest -q          # 単体テスト（エンジンなしで動く）
.venv/Scripts/python scripts/tts_status.py -c <ch> # エンジンと声
ffmpeg -hide_banner -filters | grep -E " (ass|subtitles|drawtext|xfade) "   # 字幕・クレジット・切り替えに必要
```
足りないものだけ下の手順で入れる。

## 作る

1. Python 3.11 以上で `.venv` を作り、`pip install -e ".[dev]"`（pytest つき）。`config.yaml` がなければ `config.example.yaml` をコピーする。
2. ffmpeg：`winget install Gyan.FFmpeg`（libass・drawtext つきの full build）。
3. エンジンと声：`scripts/setup_tools.py`（`coeiroink` / `aivisspeech` / `coeiroink-voice <UUID>` / `aivis-model <UUID>`）。いま使っている声の UUID は runbook 1 の表にある。
4. エンジンを起動して `scripts/tts_status.py` が全部 OK になるまで。
5. `pytest` と、承認済みの物語1本で `python -m ai_shorts -c <ch> all --id <id>` が通ることを確かめる。

## 守ること

- **ダウンロードの前に了承を得る**：何を・どこから・何 MB か（COEIROINK 約 592MB、AivisSpeech 約 217MB＋初回 約 900MB、声 0.25〜1.4GB）をまとめて伝える。システムには入れず、`tools/`（git 管理外）に置く。
- 展開は Windows 標準の `tar`（7-Zip は入れない）。`setup_tools.py` が中身のパスと（AivisSpeech は）SHA-256 を確かめる。COEIROINK の zip に入っている `.exe` は実行しない。
- AivisSpeech は `--disable_sentry` で起動する。初回はモデルと BERT を `%APPDATA%\AivisSpeech-Engine` に落とすので数分かかる。
- 版を上げるときは `setup_tools.py` の先頭の定数（版・URL）を書き換え、`docs/decisions.md` に記録する。
- 環境を消すときは `tools/` に加えて `%APPDATA%\AivisSpeech-Engine` と `%LOCALAPPDATA%\voicevox-engine` も消す（ユーザーに確認してから）。
