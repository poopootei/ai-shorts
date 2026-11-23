# ai-shorts

YouTube チャンネル「[ショートショートの世界へ](https://www.youtube.com/@ショートショートの世界へ)」の運用全般（動画づくりとチャンネルのマネジメント）を扱うリポジトリ。チャンネルの情報は [docs/channel.md](docs/channel.md)。

中心は、AIで書いたショートショートを音声合成（COEIROINK / AivisSpeech）で朗読し、縦型ショート動画（YouTube Shorts / Instagram Reels）にするローカル制作パイプライン。

- **すべてローカル・無料**（有料APIは使わない）
- **投稿は頼んだときだけ**。動画CHECK に通ったものを `upload` で予約投稿し、投稿したことを記録する（YouTube Data API、権限は投稿だけ）
- **人の CHECK は動画CHECK**：物語は Claude が書いて検査し、人は出来上がった動画で判断する（物語CHECK は D-018 でやめた）。ボツは理由と改善案を残して次に活かす
- **主な収益源は BGM**：自作BGMを TuneCore Japan 経由で YouTube Content ID に登録し、動画での使用分を得る。ショート動画そのものの広告収益は狙わない

方針の詳細は [docs/policy.md](docs/policy.md)、各工程の仕様は [docs/pipeline.md](docs/pipeline.md) を参照。
**作業の手順（環境づくり・1本作る流れ・声・読みの直し方・つまずきやすいところ）は [docs/runbook.md](docs/runbook.md)。**
Claude Code では `.claude/skills/` のスキル（`make-shorts` ほか）がこの手順を実行する。

## scripts/

| スクリプト | 用途 |
|---|---|
| `check_story.py` | 物語の検査（字数・文の長さ・hook・声）。`--readings` で読みも出す |
| `approve_story.py` | 検査に通った物語を draft → approved に移す |
| `preview_backgrounds.py` | 背景の候補シート（Openverse CC0/PDM、ID つき） |
| `fetch_stock_images.py` | 背景を取って `work/{id}/img_N.png` に置く（`--query "id:..."`） |
| `preview_video.py` | 完成動画の確認用コマ画像 |
| `tts_status.py` | エンジンが動いているか・声が入っているか |
| `voice_samples.py` | 声の聞き比べ用サンプル |
| `setup_tools.py` | エンジンと声を `tools/` に入れる |
| `start_tts.ps1` | COEIROINK と AivisSpeech を起動する |

## 処理の流れ

```
stories/draft/*.json      ← Claude Code セッションで物語を生成
      │  検査 → approve_story.py（Claude。物語CHECK はしない）
stories/approved/*.json
      │  tts → images → subs → render → qa
work/{id}/                ← 1本ごとの中間ファイル
      │  QA合格
ready/{id}.mp4            ← 動画CHECK（人）── ボツ → rejected/{id}-{n}.mp4（作り直す or 物語ごとボツ）
      │  approve-video
upload/{id}.mp4           ← 投稿待ち
      │  upload（予約投稿して記録。手で上げたら posted で記録）
posted/{id}.mp4           ← 投稿済みの原本。物語は stories/posted/
```

経緯（承認・ボツの理由と改善案・投稿先と日付・URL）は物語 JSON の `history` に残る（git 管理）。mp4 は git に入れない。

## 必要なもの

| 種類 | ツール | 備考 |
|---|---|---|
| 音声合成 | COEIROINK（50032）・AivisSpeech Engine（10101） | 声ごとに利用規約とクレジット表記を確認（下の「音声合成エンジン」） |
| 画像生成 | ComfyUI（localhost:8188） | RTX 3060 Ti（8GB）。商用利用できるモデルのみ使う |
| 合成 | ffmpeg | 字幕を焼き込むため libass つきのビルド |
| フォント | Noto Serif JP など（OFL） | `assets/fonts/` に置く |
| BGM | 自作の WAV | `assets/bgm/`。ルールは [docs/bgm.md](docs/bgm.md) |
| Python | 3.11 以上 | `pip install -r requirements.txt` |

## セットアップ

```bash
python -m venv .venv
.venv\Scripts\activate               # macOS / Linux は source .venv/bin/activate
pip install -e ".[dev]"              # src/ai_shorts をパッケージとして入れる（pytest つき）
cp config.example.yaml config.yaml   # 声・BGM・フォントなどを設定
pytest                               # 単体テスト（音声合成エンジン・ffmpeg なしで動く）
```

### 音声合成エンジン

アプリはインストールせず、エンジンだけを `tools/`（git 管理外）に置く。CPU 版にしているのは、GPU の VRAM を ComfyUI に残すため。

| エンジン | 置き場所 | 入手先 | 備考 |
|---|---|---|---|
| COEIROINK v2.13.0（CPU） | `tools/coeiroink/` | [公式サイト](https://coeiroink.com/download) の Windows CPU 版 zip。中の `.7z.001` を `tar -xf` で展開（同梱の .exe は使わない） | 声は `tools/coeiroink/speaker_info/` に置く。公式キャラはエンジンの `/v1/download_info` の URL から zip を落として展開する。**エンジンは起動時に読んだ声しか使えないので、声を足したら再起動** |
| AivisSpeech Engine 1.2.0 | `tools/aivisspeech_engine/` | [GitHub Releases](https://github.com/Aivis-Project/AivisSpeech-Engine/releases) の `.7z.001` を `tar -xf` で展開 | 声のモデルと BERT モデル（約 650MB）は `%APPDATA%\AivisSpeech-Engine` に入る。モデルは AivisHub から `/aivm_models/install` で入れる。**`--disable_sentry` で起動する**（エラー情報を外部に送らない） |
| VOICEVOX ENGINE 0.26.2（CPU） | `tools/voicevox_engine/` | GitHub の `.vvpp`（ZIP） | いまは使っていない（D-011）。`%LOCALAPPDATA%\voicevox-engine` に設定を作る |

- 起動：`powershell -ExecutionPolicy Bypass -File scripts\start_tts.ps1`（COEIROINK と AivisSpeech を別ウィンドウで起動）
- 完全に消すときは、`tools/` に加えて上の `%APPDATA%` / `%LOCALAPPDATA%` のフォルダも消す。
- 使う声は `config.yaml` の `voices` に登録し、物語 JSON の `"voice"` で選ぶ（なければ `tts.default_voice`）。`credit` は規約どおりの表記にする（説明文と画面に出る）。
- 読みやアクセントの修正は `assets/tts/user_dict.yaml` に書く。tts のたびに、使うエンジンへ反映される（COEIROINK にも同じ内容が入る）。

## 使い方

```bash
# 背景画像（ComfyUI ができるまでの仮）：段落ごとに検索語を1つ。CC0 / パブリックドメインだけを使う
python scripts/fetch_stock_images.py --id <story_id> --query "..." --query "..." --query "..."

python -m ai_shorts tts     --id <story_id>   # 声 → work/{id}/voice.wav, timing.json
python -m ai_shorts subs    --id <story_id>   # 字幕 → subs.ass, subs.json
python -m ai_shorts render  --id <story_id>   # 合成 → video.mp4
python -m ai_shorts qa      --id <story_id>   # 検査 → 合格なら ready/{id}.mp4 と ready/{id}.txt（説明文）
python -m ai_shorts all     --id <story_id>   # 上の4つを順に実行
python -m ai_shorts all     --approved        # 承認済みでまだ動画がない物語をまとめて処理

# 状態の管理（CHECK・投稿・ボツ）
python -m ai_shorts status                       # 状態ごとの一覧
python -m ai_shorts ideas                        # ボツの理由と改善案
python -m ai_shorts approve-video <id>           # 動画CHECK OK → upload/
python -m ai_shorts reject-video  <id> --reason "..." --idea "..." --remake   # 作り直す（--drop で物語ごとボツ）
python -m ai_shorts upload        --all --dry-run   # 公開の予定を見る（id を並べてもよい。1 日 1 本）
python -m ai_shorts upload        --all             # YouTube に予約投稿して記録 → posted/
python -m ai_shorts youtube-login                   # YouTube にログイン（初回・切れたとき）
python -m ai_shorts posted        <id> --platform youtube --url <URL>        # 手で投稿した → posted/
python -m ai_shorts reject-story  <id> --reason "..." --idea "..."           # 書いた物語をやめる
python -m ai_shorts revive-story  <id>           # ボツの物語を直すため draft に戻す
```

- 背景は `work/{id}/img_1.png 〜 img_N.png`。段落の数と同じなら段落の境目で切り替え、なければ単色。出典とライセンスは `work/{id}/images.json`。
- 気に入らない画像は `--skip` で差し替える（段落ごとに、上位から何枚飛ばすか）。
- images（ComfyUI）はまだない。

## フォルダ構成

```
ai-shorts/
├── CLAUDE.md              Claude Code 向けの指示
├── README.md
├── config.example.yaml
├── requirements.txt
├── docs/
│   ├── policy.md          収益化・権利・プラットフォーム規約の方針
│   ├── pipeline.md        工程ごとの仕様
│   ├── bgm.md             BGM制作と TuneCore 申請のルール
│   ├── story-guidelines.md 物語の書き方と書いたあとに確かめる点
│   └── decisions.md       決定事項の記録
├── stories/
│   ├── draft/             生成直後（検査待ち）
│   ├── approved/          検査済み（動画づくり〜投稿待ち）
│   ├── posted/            投稿済み
│   └── rejected/          ボツ（理由・改善案つき）
├── work/{id}/             中間ファイル（git 管理外）
├── ready/                 QA 合格・動画CHECK待ち（ここから下の mp4 は git 管理外）
├── upload/                動画CHECK 済み・投稿待ち
├── posted/                投稿済みの原本
├── rejected/              ボツ動画
├── assets/
│   ├── bgm/               自作BGM
│   ├── fonts/
│   └── styles/            画像生成用のスタイル指定
├── src/ai_shorts/         パイプラインのコード
├── scripts/               単発のツール
└── tests/
```
