---
name: manage-voices
description: ai-shorts の読み上げの声を選ぶ・聞き比べる・足す・物語ごとに変える。「声を変えて」「男性の声で」「この話は〇〇の声で」「声を聞き比べたい」「新しい声を試したい」「機械っぽい」「雰囲気に合う声」など、声の選択・追加・比較の依頼では必ずこのスキルを使う。エンジンの起動・状態確認（「エンジンが動かない」「接続できない」）にも使う。
---

# 声を扱う

声の一覧と規約の経緯は `docs/decisions.md`（D-011）、手順は `docs/runbook.md` の 4。Python は `.venv\Scripts\python`（以下 `py`）。

## まず状態を見る

`py scripts/tts_status.py` — エンジンが動いているか、`config.yaml` の各声がエンジンに入っているか。
止まっていれば起動する：`tools/coeiroink/engine/engine.exe`（作業フォルダ `tools/coeiroink/engine`）と `tools/aivisspeech_engine/run.exe --host 127.0.0.1 --port 10101 --disable_sentry` をバックグラウンドで。**AivisSpeech は必ず `--disable_sentry`**（エラー情報を外部に送らないため）。

## 物語の声を変える

- 物語 JSON の `"voice"` を `config.yaml` の `voices` のキーにする。書かなければ `tts.default_voice`。
- 承認済みの物語でも声だけなら変えてよいが、変えたことは伝える。反映は `py -m ai_shorts all --id <id>`（声が変わると長さも変わる）。
- いまの声：ofutonp（男性・既定）、ofutonp_kanashimi・ofutonp_yorokobi・ofutonp_aseri（スタイル違い）、tsukuyomi（女性）。新しい物語は COEIROINK だけ（D-017）。aida・aida_calm（AivisSpeech）は作り直し・比較用に残してある。ユーザーが NG とした声（VOICEVOX の冥鳴ひまり、AivisSpeech のまお・コハク・fumifumi）は使わない。

## 聞き比べ

`py scripts/voice_samples.py --id <承認済みの id> --paragraph 2 ofutonp aida coeiroink:21 aivisspeech:1310138977`
- 登録前の声は `エンジン名:スタイルID`。`work/voice_samples/00_all.wav` をユーザーに送り、端末に出る時刻の表を添える。
- セリフ（かぎかっこ）を含む段落で比べると違いが分かりやすい。
- 選ぶのはユーザー。自分の耳では判断できないので、候補と規約の違いを示して聞いてもらう。

## 声を足す

1. 候補を探す：COEIROINK は `py scripts/setup_tools.py coeiroink-voices`（UUID・大きさ・スタイル）。AivisSpeech は AivisHub（`https://api.aivis-project.com/v1/aivm-models/search?sort=download&limit=30`）。
2. **規約を確かめる**：商用利用（個人・法人）とクレジット表記。COEIROINK は `https://coeiroink.com/character/audio-character/<キャラ>` の表、AivisSpeech はモデルのライセンス（ACML 1.0 なら商用可・表記任意。ACML-NC は商用不可なので使わない）。商用不可なら入れない（収益化する動画のため）。
3. **大きさを伝えて了承を得る**（COEIROINK の声は 0.35〜1.4GB、AivisHub は約 250MB）。COEIROINK のおふとんP などはスタイルが別パック（「おふとんP+」など）に分かれている。
4. 入れる：`py scripts/setup_tools.py coeiroink-voice <UUID>` → COEIROINK を再起動（起動時に読んだ声しか使えない）／ `py scripts/setup_tools.py aivis-model <UUID>`（ライセンスとスタイル ID が出る）。
5. `config.yaml` と `config.example.yaml` の `voices` に `engine`・`style_id`・`credit`（規約どおりの表記。例 `COEIROINK:おふとんP`）を足す。
6. `py scripts/tts_status.py` が OK になることを確かめ、`docs/decisions.md` に規約の確認結果（日付つき）を書く。

## 知っておくこと

- クレジットは声の `credit` が説明文と画面左上に自動で出る（qa が説明文にあるか検査する）。
- COEIROINK・AivisSpeech は話速 1.0 で、VOICEVOX 0.92 より約1割速い。長さが 58 秒を超えると `speed_max` まで話速を上げて作り直す。
