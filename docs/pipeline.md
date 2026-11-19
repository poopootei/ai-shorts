# パイプライン仕様

すべての工程は `work/{id}/` 内のファイルを読み書きする。どの工程からでも再実行できる。

```
stories/approved/{id}.json
  → tts     → work/{id}/voice.wav, timing.json
  → images  → work/{id}/img_1.png .. img_N.png
  → subs    → work/{id}/subs.ass
  → render  → work/{id}/video.mp4
  → qa      → ready/{id}.mp4（合格時にコピー）、work/{id}/qa.json
```

## 0. 物語（stories）

Claude Code セッション内で生成する（API は使わない）。書き方は story-guidelines.md。

```json
{
  "id": "20261117-001",
  "title": "最後の自動販売機",
  "hook": "冒頭2秒で出すタイトル文（15字以内）",
  "body": "本文 250〜280字。段落は改行で区切る",
  "image_prompts": ["段落1の情景（英語）", "段落2", "段落3"],
  "tags": ["ショートショート", "朗読"],
  "voice": "ofutonp",
  "approved": false,
  "notes": "人が直した点のメモ"
}
```

- `image_prompts` の数 = 段落の数（2〜3）。
- 人が確認して `approved: true` にし、`stories/approved/` に移動する。

## 1. 音声（tts）

- 声は `config.yaml` の `voices` から、物語 JSON の `"voice"`（なければ `tts.default_voice`）で選ぶ。エンジンは COEIROINK（`/v1/estimate_prosody` → `/v1/synthesis`）か、VOICEVOX 互換の API（AivisSpeech・VOICEVOX：`audio_query` → `synthesis`）。どちらも `voices.py` で同じ形にそろえている。
- 使った声とクレジットは `timing.json` の `voice` / `credit` に残し、render（画面の表記）と qa（説明文）はそこから読む。
- 設定：`speaker_id`、`speed`（初期値 0.92）、`pause_between_sentences`（0.5秒）、`pre/post_silence`（各1.0秒）。
- 文ごとに合成してつなぐと、文の間の無音を制御しやすい。
- `timing.json`：文ごとの `{text, paragraph, start, end}` と段落ごとの `{start, end}` を出力する。時刻は合成した音声の実際の長さから計算する（文の前後の無音 prePhonemeLength / postPhonemeLength はエンジンの既定 0.1 秒のまま。文と段落の間の無音はこちらで足す）。字幕を文より細かく区切るときは、文の中で字数に比例して割り振る。
- 段落の境目の無音は `pause_between_paragraphs`（初期値 0.8秒）。出力は 48kHz モノラル。
- 長さの制御：合計が **58秒** を超えたら speed を 0.03 刻みで最大 1.05 まで上げて再合成。それでも超えたら失敗として止め、本文の短縮を求める。
- 読み上げる文からはかぎかっこを外す（エンジンが前後に間を入れるため）。「勇気」「眠り」のように並ぶものは読点でつなぐ。字幕には元の文を使う。
- 読み間違い・アクセントの誤りは `assets/tts/user_dict.yaml` に書く。tts のたびに、使うエンジンのユーザー辞書をこの内容にそろえる（VOICEVOX 互換はないものを消す。COEIROINK は `/v1/set_dictionary` でまるごと置き換える）。
- 読みの確認：VOICEVOX 互換は audio_query の `kana`（平板も最後のモーラに `'` が付く）、COEIROINK は `CoeiroinkClient.reading()`。数字（十八歳など）は辞書より先に読みが決まるので、辞書では直らない。

## 2. 背景（images）

- ComfyUI の API（localhost:8188）でワークフロー JSON を送る。
- 段落ごとに1枚、1080×1920（または生成しやすい解像度で作って拡大）。
- スタイル指定は `assets/styles/{style}.txt` に固定し、`image_prompts` の前に連結する。絵柄をそろえる。
- seed を `work/{id}/images.json` に記録し、作り直しを再現できるようにする。
- 生成できない場合の代替：Pexels API（無料キー、商用可）。

## 3. 字幕（subs）

- ASS 形式。`timing.json` から1行12〜15字で区切る。句読点で優先的に区切る。
  - 区切れる位置は、句読点の後と「ひらがな → 漢字・カタカナ」の切れ目。その中から、行数が少なく長さがそろうように選ぶ。
  - 句読点以外での区切り（「背を｜測り」）、かぎかっこの途中（「少し｜休んで」）、」の直後の助詞で始まる行（「勇気」｜を）は避ける。罰の重さは `subs.py` の定数。
  - 文末の「。」は字幕に出さない。字幕1件 = 1行で、文の時間を字数に比例して割り振る。
- フォント：明朝体（Noto Serif JP など）、白文字＋黒の縁取り。
- 位置：**画面の中央〜やや上**。下20%と右端はアプリの表示と重なるので置かない。
- 冒頭2秒は `hook` を大きく表示する。

## 4. 合成（render）

- ffmpeg。1080×1920、30fps、H.264（yuv420p）、AAC 192kbps。
- 画像：ゆっくりズーム（zoompan 1.0→1.08）、段落の切り替えで 0.5秒のクロスフェード。各画像の表示時間は timing.json の段落の境目に合わせる。
- 音声：声 + BGM。BGM は**曲の頭から**使い、`bgm_gain_db` で一定の音量にする（声に合わせて下げる処理は、Content ID の検出テストが済むまで入れない。bgm.md 参照）。
- 声と BGM は numpy で混ぜ（`work/{id}/mix.wav`）、pyloudnorm で −14 LUFS に揃えたあと、`limiter_knee` を超える波形を tanh でなだらかに押さえる。ffmpeg は映像と mix.wav を合わせるだけ。
- ズームは zoompan ではなく、フレームごとに scale → crop する（zoompan は小刻みに揺れるため）。
- `img_1.png` がなければ単色の背景（`background_color`）で作る。
- 声のクレジット（`timing.json` の `credit`）を画面の左上に小さく出す（`show_credit_overlay` で切り替え）。

## 5. 検査（qa）

自動で検査し、結果を `work/{id}/qa.json` に書く。すべて合格したら `ready/{id}.mp4` にコピーする。

| 項目 | 基準 |
|---|---|
| 長さ | ≤ 59.0 秒 |
| 解像度 | 1080×1920 |
| 音量 | −14 LUFS ± 1 |
| 字幕 | 画面外へのはみ出しなし、1行の字数 ≤ 15 |
| クレジット | 説明文に声のクレジット（`timing.json` の `credit`）がある |
| 承認 | 元の物語が approved: true |

あわせて、投稿用の説明文 `work/{id}/description.txt`（タイトル、本文の要約、タグ、クレジット）を出力する。

## 最初のマイルストーン

1. 物語1本を手で書いて approved に置く
2. tts → render を最小構成で通す（画像は1枚、字幕なしでよい）
3. 字幕と複数枚の画像を足す
4. スマホで見て、字幕の位置・BGMの音量・話速を config で調整する
5. qa を入れて、まとめて処理できるようにする
