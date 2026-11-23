---
name: fix-readings
description: ai-shorts の読み上げの読み間違い・アクセントの誤りを確かめて、assets/tts/user_dict.yaml の辞書で直す。「読み間違えてる」「〇〇を△△と読んでる」「アクセントが変」「イントネーションがおかしい」「読みを確認して」など、音声の読みに関する指摘や確認では必ずこのスキルを使う。COEIROINK・AivisSpeech・VOICEVOX のどれにも同じ辞書が効く。
---

# 読みを直す

Python は `.venv\Scripts\python`（以下 `py`）。エンジンが動いている必要がある（`py scripts/tts_status.py`）。

## 手順

1. 読みを出す：`py scripts/check_story.py <id> --readings`
   - 物語の声のエンジンで読む。COEIROINK はひらがな、AivisSpeech / VOICEVOX はカタカナ（`'` がアクセント位置。平板も最後のモーラに `'` が付くので、それだけでは誤りではない）。
   - ユーザーの指摘がある語を探し、ほかにも誤りがないか全文を見る。
2. 辞書に足す：`assets/tts/user_dict.yaml`

```yaml
- surface: 小部屋        # 表記
  pronunciation: コベヤ  # カタカナ（ひらがなは COEIROINK で効かない）
  accent_type: 0         # 音が下がる直前のモーラの位置。0 = 平板。例: カ/ン/コ'/ー/ヒ/ー → 3
```

3. もう一度 1 を実行して直ったか確かめる（辞書は check_story / tts のたびにエンジンへ反映される）。
4. 動画に反映：`py -m ai_shorts all --id <id>`（読みが変わると長さも変わるので tts からやり直す）。

## 辞書で直らないとき

- **数字**（「十八歳」→ じゅう/はっさい など）：数字の読みは辞書より先に決まる。かなで書くか、言い回しを変える。
- **1字の語や、ほかの語にも効いてしまう語**（「柄」→ え／がら）：辞書に入れるとほかの文が壊れる。文を書き換える（例：「同じ柄だった」→「まったく同じだった」）。
- 物語の本文を変えるのは、動画CHECK に出す前なら Claude の判断でよい（物語CHECK はしない。D-018）。動画CHECK に出したあと（ready・upload・投稿済み）の文章を変えるときは**ユーザーに確認してから**。直したら notes に書く。

## 知っておくこと

- 読み上げではかぎかっこを外している（エンジンが前後に間を入れるため）。字幕は元の文。
- COEIROINK は辞書をエンジンに保存しないので、毎回まるごと送っている。AivisSpeech / VOICEVOX はエンジン側の辞書を YAML とそろえる（YAML にない語は消える）。
