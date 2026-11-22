---
name: write-stories
description: ai-shorts の朗読用ショートショート（250〜280字）を書いて stories/draft/ に保存し、検査し、ユーザーの承認を受けて stories/approved/ に移す。「物語を書いて」「ネタを〇本」「下書きを作って」「承認する」「この話を直して」「draft を確認」など、物語の作成・修正・承認に関わる依頼では必ずこのスキルを使う。動画まで作る依頼なら make-shorts の中でこの手順を使う。
---

# 物語を書く・承認する

書き方の決まりは `docs/story-guidelines.md`（必ず読む）。Python は `.venv\Scripts\python`（以下 `py`）。

## 書く

0. `py -m ai_shorts ideas` で、これまでのボツの理由と改善案を読む。同じ理由でボツになりそうな筋・書き方を避ける。
1. ジャンルを散らす（SF・日常の不思議・ブラックユーモア・ほっこり など）。既存作品の筋やオチを借りない、作家名で「〜風」にしない。
2. 形：冒頭の1文で「おかしい」と思わせる → 状況 → ひねり → 最後の1文でオチ。登場人物は1〜2人、固有名詞は少なく。
3. 耳で聞く文章にする：1文 40 字以内、同音異義語・難読漢字を避ける。数字は読みが辞書で直せないので、迷う読み（「十八歳」など）は避けるか、かなで書く。
4. JSON を `stories/draft/{YYYYMMDD-NNN}.json` に保存（形式は `docs/pipeline.md` の 0）。
   - `id` = ファイル名。日付は作った日、連番は `stories/` の既存（draft・approved・posted・rejected のすべて）と重ならないように。
   - `hook` は 15 字以内（画面では 8 字ずつ折り返す）。
   - `image_prompts` は段落の数だけ。`notes` に背景の検索語の候補（英語の短い語）を書く。
   - `"voice"` に雰囲気に合う声を `config.yaml` の `voices` から選ぶ（COEIROINK だけ。D-017。男性の語り手なら ofutonp とそのスタイル違い ofutonp_kanashimi / ofutonp_yorokobi / ofutonp_aseri、女性なら tsukuyomi。話ごとに散らす）。
   - `"approved": false`。
5. 検査：`py scripts/check_story.py stories/draft/<id>.json --readings`（エンジンが止まっていたら `--readings` なしで、あとで読みを確かめる）
   - NG は直す。字数は 250〜280 字に入れる（足りない・多いときは文を足し引きする）。
   - 読み間違いは fix-readings スキルで辞書に足す。辞書で直らないものは文を書き換える。

## 承認を求める

- 下書きの**全文**（タイトル、hook、本文、声）をそのまま見せる。字数と、直した読みも添える。
- 「既存の有名作品に似すぎていないか」「不快な表現・実在の人物や団体への言及がないか」はユーザーにも見てもらう（自分では確かめきれない）。
- 承認はユーザーの言葉で受ける。待っている間に背景や合成へ進まない。

## 承認されたら

- `py scripts/approve_story.py <id> [<id> ...] --note "直した点"`（直していなければ `--note` なし）
  - ユーザーが直しを指示したら、draft を直して再検査し、見せ直してから承認する。
  - 声を変えるよう言われたら `--voice <key>`。
- 検査で NG があると承認されず draft に残る（エラーを直してやり直す）。

## ボツになったら

- 理由と改善案をユーザーの言葉で聞き取り、`py -m ai_shorts reject-story <id> --reason "..." --idea "..."` で `stories/rejected/` に移す（消さない。改善案としてためる）。
- ボツの話を直すときは `py -m ai_shorts revive-story <id>` で draft に戻してから直し、もう一度承認を求める。

## なぜ人の承認を通すか

YouTube の「オーセンティックでないコンテンツ」（量産・繰り返し）に当たらないよう、人の選別と修正を必ず入れる方針（`docs/policy.md`）。だから Claude は書くところまでで、承認は人がする。
