# CLAUDE.md

このリポジトリは、AIで書いたショートショートの朗読ショート動画を作るローカルパイプライン。概要は README.md、方針は docs/ にある。作業前に関係する docs を読むこと。

## 絶対に守ること

1. **有料APIを使わない。** LLM、TTS、画像生成はすべてローカルか Claude Code セッション内で済ませる。外部へのHTTP通信が必要な新しい依存を足す前に、ユーザーに確認する。
2. **自動投稿は作らない。** 出力は `ready/{id}.mp4` まで。YouTube Data API は、審査を通っていないプロジェクトから投稿すると非公開に固定されるため使わない（docs/decisions.md D-003）。
3. **動画は59秒以下。** Content ID の申し立てが付いた1分超のショートはブロックされる。QA でここを必ず検査する。
4. **BGM の作曲を Claude がしない。** メロディ・和音・構成はユーザーが決めたもの（MIDI）を使う。Claude が作ってよいのはシンセエンジン（音色、エンベロープ、エフェクト）とレンダリングのコードだけ。生成AI楽曲は TuneCore Japan の Content ID に登録できないため（docs/bgm.md）。
5. **第三者の音源素材を BGM に入れない。** ループ、サンプルパック、SoundFont、効果音素材は使わない。音は numpy で合成して WAV に直接書き出す。
6. **物語は人の承認を通す。** `approved: true` で `stories/approved/` にあるものだけを処理する。生成した物語を自動で承認しない。
7. **画像生成モデルは商用利用できるものだけ。** 新しいモデルを使う前に、ライセンスを docs/decisions.md に記録する。

## コードの方針

- Python 3.11 以上、パッケージは `src/ai_shorts/`。CLI は `python -m ai_shorts <stage>`。
- 工程（tts / images / subs / render / qa）は独立したモジュールにし、入出力は `work/{id}/` 内のファイルだけでつなぐ。どの工程からでも再実行できるようにする。
- 設定値はコードに直接書かず `config.yaml` から読む。
- 外部ツール（COEIROINK・AivisSpeech などの音声合成エンジン、ComfyUI、ffmpeg）を呼ぶ部分は薄いラッパーにまとめ、接続できないときは分かりやすいエラーで止める。
- 生成物（wav、png、mp4）は git にコミットしない。

## 手順書とスキル

作業の手順は [docs/runbook.md](docs/runbook.md) にまとめてある。作業のルートは `D:\prj\ai-shorts`、Python は `.venv\Scripts\python`。
Claude Code では、依頼に合うスキル（`.claude/skills/`）を使って手順どおりに進める。

| 依頼 | スキル |
|---|---|
| 動画を作る・作り直す（全体） | `make-shorts` |
| 物語を書く・直す・承認する | `write-stories` |
| 背景画像を選ぶ・差し替える | `pick-backgrounds` |
| 読み間違い・アクセントを直す | `fix-readings` |
| 声を選ぶ・比べる・足す、エンジンの起動 | `manage-voices` |
| 環境を作る・作り直す・確かめる | `setup-environment` |

- 音声合成エンジンはセッションが終わると止まる。作業の最初に `scripts/tts_status.py` で確かめる。
- ダウンロード（エンジン・声）は大きいので、何を・どこから・何 MB かを伝えて了承を得てから。

## 作業の進め方

- 最初の目標は「1本を最後まで通す」こと。各工程の作り込みより、まず全工程を最小限で通す。
- 見た目や音量の調整は、ユーザーがスマホで確認して判断する。数値の変更は config で行う。
- 方針に関わる判断をしたら docs/decisions.md に追記する。

## 用語

- **物語 (story)**: 250〜280字のショートショート。`stories/*/{id}.json`
- **work/{id}/**: 1本分の中間ファイル置き場
- **ready/**: QA に合格した完成品
