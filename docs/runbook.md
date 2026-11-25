# 運用手順書（runbook）

動画を作るときの手順を、毎回同じ結果になるようにまとめたもの。
方針は [policy.md](policy.md)、工程の仕様は [pipeline.md](pipeline.md)、決定の経緯は [decisions.md](decisions.md)。
Claude Code で作業するときは、`.claude/skills/` のスキル（下の表）がこの手順を実行する。

| やること | スキル | この文書の節 |
|---|---|---|
| 動画を作る（全体の流れ） | `make-shorts` | 3 |
| 動画CHECK・投稿の記録・ボツ・状況の一覧 | `review-and-post` | 3-5〜3-7 |
| 物語を書く・承認する | `write-stories` | 3-1〜3-2 |
| 背景画像を選ぶ | `pick-backgrounds` | 3-3 |
| 読み間違いを直す | `fix-readings` | 5 |
| 声を選ぶ・足す | `manage-voices` | 4 |
| 環境を作る・作り直す | `setup-environment` | 1 |

作業のルートは `D:\prj\ai-shorts`。コマンドはすべてここで実行する。Python は `.venv\Scripts\python`。

**チャンネル**：`<ch>` はチャンネル名（`shortshort` / `nihongo` / `aozora`。CLAUDE.md の「チャンネル」）。`python -m ai_shorts` とスクリプトには `-c <ch>` を付ける。この文書の `stories/`・`work/`・`upload/`・`config.yaml` などのパスは、`channels/<ch>/` から見たもの。

---

## 1. 環境を作る（新しい PC・作り直し）

ダウンロードは合計で数 GB になる。**実行する前に、何をどこから・何 MB 落とすかを伝えて了承を得る。**

| 手順 | コマンド | 大きさ |
|---|---|---|
| Python の環境 | `python -m venv .venv` → `.venv\Scripts\python -m pip install -e ".[dev]"` | 数十 MB |
| 設定 | チャンネルごとに `copy channels\<ch>\config.example.yaml channels\<ch>\config.yaml` | – |
| ffmpeg | `winget install Gyan.FFmpeg`（libass・drawtext つきの full build） | 約 200MB |
| COEIROINK | `.venv\Scripts\python scripts\setup_tools.py coeiroink` | 約 592MB（展開後 1.4GB） |
| AivisSpeech | `.venv\Scripts\python scripts\setup_tools.py aivisspeech` | 約 217MB（＋初回起動時に約 900MB） |
| エンジン起動 | `powershell -ExecutionPolicy Bypass -File scripts\start_tts.ps1` | – |
| 声：おふとんP | `.venv\Scripts\python scripts\setup_tools.py coeiroink-voice a60ebf6c-626a-7ce6-5d69-c92bf2a1a1d0` → COEIROINK を再起動 | 1.39GB |
| 声：阿井田 茂 | `.venv\Scripts\python scripts\setup_tools.py aivis-model 47e53151-a378-46f3-abee-ce13aa07feb1` | 約 250MB |
| 確認 | `.venv\Scripts\python scripts\tts_status.py` → 全部 OK | – |
| テスト | `.venv\Scripts\python -m pytest` | – |

- フォント（Noto Serif JP Medium、OFL）は `assets/fonts/` に入っている（git 管理）。
- つくよみちゃんは COEIROINK に同梱。
- エンジンのデータは `tools/` のほか、`%APPDATA%\AivisSpeech-Engine`（モデルと BERT、約 1.6GB）にもできる。完全に消すときはそこも消す。
- VOICEVOX（`tools/voicevox_engine/`）はいまは使っていない（D-011）。

## 2. 作業を始めるとき

1. エンジンを起動する：`powershell -ExecutionPolicy Bypass -File scripts\start_tts.ps1`
   - Claude Code から起動するときは、バックグラウンドで `tools/coeiroink/engine/engine.exe`（作業フォルダは `tools/coeiroink/engine`）と `tools/aivisspeech_engine/run.exe --host 127.0.0.1 --port 10101 --disable_sentry` を動かす。**セッションが終わると止まる**ので、次の作業のときは起動し直す。
2. 状態を確かめる：`.venv\Scripts\python scripts\tts_status.py`（止まっている・声がないものは NG）

## 3. 1本（または数本）作る流れ

```
物語（Claude が書いて検査・承認）→ 背景 → 合成・QA → 動画CHECK（人）→ 投稿（人）→ 記録
                                   └ 3D の物語（visual: 3d）は、背景の代わりに 3D の舞台（3-3b）
```

| 状態 | 物語 | 動画 | 次にやること |
|---|---|---|---|
| 下書き | `stories/draft/` | – | 検査に通して approve_story.py で承認（物語CHECK はしない） |
| 動画づくり待ち／QA NG | `stories/approved/` | `work/<id>/` | 背景を選んで合成（3D の物語は舞台を書いて書き出す。一覧では題に［3D］） |
| 動画CHECK待ち | `stories/approved/` | `ready/` | スマホで見て OK かボツ |
| 投稿待ち | `stories/approved/` | `upload/` | YouTube Studio で投稿 |
| 投稿済み | `stories/posted/` | `posted/` | – |
| ボツ | `stories/rejected/` | `rejected/<id>-<n>.mp4` | 改善案として残す |

- いまの状態：`.venv\Scripts\python -m ai_shorts -c <ch> status`
- ボツの理由と改善案：`.venv\Scripts\python -m ai_shorts -c <ch> ideas`。**物語を書く前と動画を作る前に読む。**
- 経緯は物語 JSON の `history`（承認・ボツ・投稿の日付と内容）。git で残る。

### 3-1. 物語を書く（Claude Code セッション内）
- [story-guidelines.md](story-guidelines.md) に沿って書き、`stories/draft/{YYYYMMDD-NNN}.json` に保存する。id は作った日付＋連番。
- `"voice"` に雰囲気に合う声の候補を入れる（`config.yaml` の `voices`）。
- 3D で作るなら `"visual": "3d"`（目安は 3-3b）。書かなければ静止画。
- `image_prompts` は段落の数だけ（英語）。`notes` に背景の検索語の候補を書いておくと次が楽。
- 検査：`.venv\Scripts\python scripts\check_story.py stories\draft\<id>.json --readings`
  - NG を直す。読み間違いは 5 の手順で辞書に足す（辞書で直らないものは文を書き換える）。

### 3-2. 承認（Claude。物語CHECK はしない）
- 人の確認は動画CHECK だけ（decisions.md D-018）。Claude が story-guidelines.md の確認点を見て直し、検査に通ったら承認する。
- `.venv\Scripts\python scripts\approve_story.py <id> [<id> ...]`（検査に NG があると承認されず draft に残る）
- 書いてみてやめる物語は：`.venv\Scripts\python -m ai_shorts -c <ch> reject-story <id> --reason "理由" --idea "改善案"` → `stories/rejected/`。
  - 動画CHECK で物語ごとボツになったら `reject-video <id> ... --drop`（3-5）。直して出し直すときは `revive-story <id>` で draft に戻す。

### 3-3. 背景画像（ComfyUI ができるまでの仮。D-008）
1. 候補を並べる：`.venv\Scripts\python scripts\preview_backgrounds.py --name <id> "検索語1" "検索語2" "検索語3"`
   - `work/_previews/<id>_sheet.png` を見て、段落ごとに1枚選ぶ。端末に出る ID を控える。
   - 合うものがなければ検索語を変える。英語の短い語（2〜3語）が当たりやすい。縦長で雰囲気の合う CC0 は少ない。
   - 広告・ブランドロゴ・実在の人物が目立つもの、絵柄が浮くもの（古い図版など）は避ける。
2. ID で取る：`.venv\Scripts\python scripts\fetch_stock_images.py --id <id> --query "id:<ID1>" --query "id:<ID2>" --query "id:<ID3>"`
   - 出典とライセンスは `work/<id>/images.json` に残る。

### 3-3b. 3D の舞台（visual: 3d の物語。D-027・D-028）
- 3D に向く話：場所がひとつか2つ、人が3人まで、動きが部品にあるもの（座る・立つ・歩く・手を物にのせる・物を持つ・うなずく／首をかしげる）、小物が箱・瓶・札くらいの形。向かない話：人ごみ（満員電車・行列・店の客）、場所をいくつも移る話、宇宙・動物など部品にないもの。
- 準備（一度だけ）：Blender 5.2 LTS を `D:\blender` に置き、`config.yaml` に `blender:`（`config.example.yaml` を写す）を足す。足していなければ `--blender D:\blender\blender.exe` を付ける。
- 流れ：
  1. `.venv\Scripts\python -m ai_shorts -c <ch> all --id <id>`：3D の物語は tts → subs → render（声・BGM・字幕）で止まる。背景画像は選ばない。
  2. 舞台 `scripts/blender/<id>.py` を書く（部品は `scripts/blender/kit.py`、例は既存の舞台）。
  3. 下見：`.venv\Scripts\python scripts\render_3d.py -c <ch> <id> --stills 1,10,20,30 --scale 40` → `work/<id>/3d/still_*.png` を見て直す（数秒〜2分）。
  4. 全編：`.venv\Scripts\python scripts\render_3d.py -c <ch> <id>` → `work/<id>/video_3d.mp4`（1本 8〜12 分）。
  5. 採用：`... render_3d.py -c <ch> <id> --adopt` → `qa`。qa は、3D の物語で 3D 版を採用していないと「映像」で NG にする。
- 静止画で作った物語を 3D に作り直すときも同じ（`--adopt` が前の版を `video_static.mp4` に残す）。
- 人形は自前の4体（D-029）を使う：`kit.person("young_man")`（ほかに young_woman / old_man / old_woman）。これが標準で、説明文の「映像：」は `blender.credit`（3D（Blender））になる。
  - 既存の4本の舞台（20261123-007・008、20261124-002・003）は D-029 より前の Quaternius の人形（`casual_man.glb`）。段取りの手本にはしてよいが、人形はそこから写さない。自前の人形の使い方の手本は `scripts/blender/people_check.py`。
  - 服の色を物語ごとに変える：`kit.person("young_man", "me", colors={"top": (0.1, 0.2, 0.5)})`（材質は skin / hair / brow / top / inner / bottom / shoes / detail）。
  - 表情：`c.expr(F(t), smile=1)`（blink / smile / open / surprise / angry / sad。0 で戻す）、`c.blinks(1, F(終わり))`、セリフの口パク `c.talk(F(t0), F(t1))`。
  - 人形を直す・足す：`scripts/blender/make_characters.py` の SPECS を直して書き出す → `scripts/blender/people_check.py --out <フォルダ>` で座る・立つ・歩く・表情を下見し、ひじ・ひざの向き（POLES の行）を確かめる。

### 3-4. 合成
- `.venv\Scripts\python -m ai_shorts -c <ch> all --id <id>`（tts → subs → render → qa）
  - 一部だけやり直すとき：`subs` / `render` / `qa` を個別に。字幕や画像を変えただけなら tts は不要。
  - 「上限を超えています」で止まったら本文を短くする（話速は `speed_max` まで自動で上がる）。

### 3-5. 動画CHECK（人）
- `qa` の全項目が OK で `ready/<id>.mp4` と `ready/<id>.txt`（説明文）ができる。
- 見た目：`.venv\Scripts\python scripts\preview_video.py <id>` → `work/<id>/preview.png`（hook・各段落・最後のコマ）。字幕の読みやすさは `--crop`。
- ユーザーに動画を渡す。字幕の大きさ・BGM の音量などの判断は、ユーザーがスマホで見て決める（数値は `config.yaml`）。
- OK なら：`.venv\Scripts\python -m ai_shorts -c <ch> approve-video <id> --note "コメント"` → `upload/`（投稿待ち）。**Claude が自分で OK にしない。**
- ボツなら：`.venv\Scripts\python -m ai_shorts -c <ch> reject-video <id> --reason "理由" --idea "改善案" --remake`
  - 動画は `rejected/<id>-<n>.mp4` に残る（n は何回目のボツか）。`--remake` は物語を approved に残して作り直す。`--drop` は物語ごとボツ。

### 3-6. 投稿（予約投稿）
投稿するのは、ユーザーが「投稿して」と言ったときだけ（CLAUDE.md の2、D-015）。

はじめに一度だけ（ユーザーが行う）：
1. Google Cloud Console でプロジェクトを作り、「YouTube Data API v3」を有効にする。
2. OAuth 同意画面（Google Auth Platform）を作る。対象は「外部」。公開ステータスを「本番環境」にする（「テスト」のままだとログインが 7 日で切れる）。Google の確認（審査）は申し込まなくてよい。
3. OAuth クライアント ID を作る（種類は「デスクトップ アプリ」）。JSON をダウンロードして `secrets/youtube_client_secret.json` に置く（`secrets/` は git 管理外）。
4. `config.example.yaml` の `youtube:` を `config.yaml` にコピーし、公開時刻（`publish_time`）などを決める。
5. `.venv\Scripts\python -m pip install -r requirements.txt`
6. `.venv\Scripts\python -m ai_shorts -c <ch> youtube-login` → ブラウザでチャンネルの Google アカウントを選ぶ。「Google はこのアプリを確認していません」と出たら「詳細」→「（アプリ名）に移動」。`secrets/youtube_token.json` ができる。

投稿するとき：
- まず予定を見せる：`.venv\Scripts\python -m ai_shorts -c <ch> upload --all --dry-run`（id を並べてもよい。公開はその順に 1 日 1 本）。外部には何も送らない。
- 了承をもらったら `--dry-run` を外して実行する。1 本ずつ上げて、`posted` の記録（URL・公開日）まで行う。途中で止まったら、残りは `upload/` に残る（記録したものが二重に上がることはない）。
- 公開日は、これまでの YouTube の公開日（`stories/posted/` の history）の翌日から。早くても今から `min_lead_minutes` 先の枠。`--start YYYY-MM-DD` で決めてもよい。
- 上げたら YouTube Studio で、予約の日時と、ショートとして扱われているかを確かめる。Studio で公開日を変えたら、`stories/posted/<id>.json` の history の date も直す。
- **BGM の Content ID は公開前に確かめる。** Content ID はアップロードした時点で調べられるので、非公開・予約のままでも結果が出る。API からは読めないので Studio で見る。終わるまでの時間は決まっていないので、公開の1日以上前に上げておく。
  1. Studio →「コンテンツ」→「ショート」タブ → フィルタで「申し立て」。
  2. 「制限」の列の「申し立て」にカーソルを当てて「詳細を表示」→「使用されているコンテンツ」の「詳細を表示」。
  3. 正しく紐づいていれば、自分の曲名・申し立て者（TuneCore Japan など）・対応「収益化」が出る。
  - 申し立てがない：検出されていない（BGM の音量が小さい、登録がまだ有効でない、など）。曲の別の部分や別の権利者が出ている：BGM を見直す。どちらも、公開日までに Studio で予約を外すか日時をずらし、ユーザーと対応を決める。
  - 動画は59秒以下なので、申し立てが付いてもブロックはされない（ブロックされるのは1分を超えるショート）。
  - 公開後に申し立てが付くこともある（YouTube からメールが来る）。
- 「ログインが切れています」と出たら `youtube-login` をやり直す。

手で上げるとき：YouTube Studio で `upload/<id>.mp4` を上げ、説明欄に `upload/<id>.txt` を貼る。そのあと 3-7 で記録する。

タブレットから上げるとき（D-016）：
1. `.venv\Scripts\python -m ai_shorts -c <ch> share` で `upload/` を MiniPC に送る（初回と `share_app/server.py` を変えたときは `--install` を付ける）。
2. タブレットのブラウザで `share.url`（http://192.168.1.7:8040/）を開く。「動画を保存」で mp4 を保存し、YouTube アプリで上げる。タイトル・説明文は「コピー」で貼る。予約の日時の目安も出る（`youtube:` の設定があるとき）。
3. 上げたら「投稿した」で公開日（予約なら公開される日）と URL を送る。見てやめるなら「ボツ」で理由・改善案・作り直すか物語ごとかを送る。次の `share` がこのPCの記録にして（`posted` / `reject-video` と同じ）、MiniPC から消す。`share` までは「取り消す」で戻せる。
   - ボツで改善案が空なら記録されず、`share` が「要対応」と出す。改善案を決めて `reject-video` で記録する。
   - 記録が増えるので、`share` のあとはコミットする。
- 接続できないとき：MiniPC が起きているか、`ssh lenovo` が通るかを見る。ページが開かないときは MiniPC で `systemctl --user status ai-shorts-share`。
- iPad の Safari では、保存した動画は「ファイル」に入る。YouTube アプリで選ぶには、共有メニューの「ビデオを保存」で写真に入れる。
- BGM：方針は自作 BGM（`assets/bgm/`、[bgm.md](bgm.md)）。Studio のエディタ（「音声」）で後付けできるのは YouTube オーディオライブラリの曲だけで、自作曲の Content ID 収益にはつながらない。

### 3-7. 投稿の記録
- `upload` で上げたものは記録済み。手で上げたとき・ほかの場所に上げたときは：`.venv\Scripts\python -m ai_shorts -c <ch> posted <id> --platform youtube --url <URL> [--date 公開日]`
  - mp4・txt は `posted/` へ、物語は `stories/posted/` へ移る。予約投稿なら `--date` は公開日。
  - ほかの場所にも上げたら、`--platform instagram` などでもう一度実行（記録が足されるだけ）。
- `posted/`・`rejected/` の mp4 は git に入らない。消すとき・バックアップはユーザーが決める。
- `all --approved` は、`ready/`・`upload/` に動画がある物語を飛ばす（作り直すときは `--id` で）。

## 4. 声

- 使える声は `config.yaml` の `voices`。物語 JSON の `"voice"` で選ぶ（なければ `tts.default_voice`）。
- いまの声（D-011）：`ofutonp`（男性・既定）、`ofutonp_kanashimi`、`tsukuyomi`（女性）、`aida`・`aida_calm`（男性、AivisSpeech）。
- 聞き比べ：`.venv\Scripts\python scripts\voice_samples.py --id <承認済みの id> --paragraph 2 ofutonp aida coeiroink:21`
  - `エンジン名:スタイルID` で未登録の声も試せる。`work/voice_samples/00_all.wav` に順につながる。
- 声を足す：
  1. 一覧を見る：`setup_tools.py coeiroink-voices`（COEIROINK 公式）／ AivisHub（`https://hub.aivis-project.com`）
  2. 規約を確認する（商用利用・クレジット表記）。COEIROINK はキャラのページ、AivisHub はモデルのライセンス（ACML なら商用可・表記任意）。
  3. 大きさを伝えて了承を得てから入れる（1 の表のコマンド）。COEIROINK は入れたら再起動。
  4. `config.yaml` と `config.example.yaml` の `voices` に、`engine`・`style_id`・`credit`（規約どおりの表記）を足す。
  5. `scripts/tts_status.py` で OK を確かめ、`decisions.md` に規約の確認結果を書く。

## 5. 読み間違い・アクセント

- 確かめる：`.venv\Scripts\python scripts\check_story.py <id> --readings`（物語の声のエンジンで読む）
- 直す：`assets/tts/user_dict.yaml` に足す。次の tts から、使うエンジン（COEIROINK にも）へ反映される。

```yaml
- surface: 小部屋
  pronunciation: コベヤ   # カタカナ
  accent_type: 0          # 音が下がる直前のモーラの位置。0 = 平板
```

- 辞書で直らないもの：数字（「十八歳」など。数字の読みは辞書より先に決まる）、ほかの言葉にも効いてしまう1字の語（「柄」→ え／がら）。この場合は文を書き換える。
- 字幕は元の文のまま。読み上げだけかぎかっこを外している（エンジンが前後に間を入れるため）。

## 6. つまずきやすいところ

| 症状 | 原因と対処 |
|---|---|
| `エンジンに接続できません` | エンジンが止まっている（セッション終了で止まる）。2 の手順で起動 |
| COEIROINK で `500` / `KeyError` | 起動後に足した声。COEIROINK を再起動する |
| `tts_status.py` で NG | 声が入っていないか、`style_id` の間違い。エンジンの話者一覧で確かめる |
| Openverse が `504` | 混んでいる。スクリプトは数回やり直す。だめなら少し待つ |
| 選んだ画像と違う画像が来た | 検索結果の順番が変わった。`id:` で指定する |
| 端末の日本語が文字化けする | Git Bash からは `PYTHONIOENCODING=utf-8` を付ける。`python -I` のときは環境変数が効かないので `python -I -X utf8` |
| ffmpeg の drawtext / subtitles がパスで失敗 | Windows のドライブ文字の `:` が原因。render は root で ffmpeg を動かして相対パスを渡している |
| 動画が 59 秒を超えそう | 本文を短くする。目安は 250〜280 字（いまの声で 45〜52 秒） |

## 7. 外部とのやりとり

- 有料 API は使わない。外部への通信は、ダウンロード（エンジン・声・フォント）と Openverse の画像検索・取得だけ。
- AivisSpeech は必ず `--disable_sentry` で起動する（エラー情報の外部送信を切る）。
- `share` は LAN の MiniPC に ssh で送るだけで、インターネットには出ない（D-016）。
- アプリ内ブラウザで YouTube Music などを開くと音が鳴ることがある。調べ終わったらタブを閉じる。
