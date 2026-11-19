---
name: review-and-post
description: ai-shorts の動画CHECK（ユーザーが見て OK / ボツ）、投稿の記録、ボツ（物語・動画）の理由と改善案の記録、状況の一覧を扱う。「この動画OK」「動画をボツに」「作り直して」「投稿した」「アップした」「URL はこれ」「投稿待ちは？」「いまの状況」「ボツの一覧」「改善案を見せて」「ボツにした話を直したい」など、作ったあとの確認・投稿・ボツの管理では必ずこのスキルを使う。物語の承認そのものは write-stories、動画を作るのは make-shorts。
---

# 動画CHECK・投稿・ボツを記録する

流れと根拠は `docs/runbook.md` の 3-5〜3-7。Python は `.venv\Scripts\python`（以下 `py`）。
状態はフォルダで決まり、経緯は物語 JSON の `history` に残る（git 管理）。

```
stories/draft ─物語CHECK─▶ stories/approved ─作る─▶ ready/ ─動画CHECK─▶ upload/ ─投稿（人）─▶ posted/ + stories/posted
      │ボツ                                             │ボツ
      ▼                                                 ▼
stories/rejected（理由・改善案）                     rejected/{id}-{n}.mp4（物語は approved に残すか rejected へ）
```

## いまの状況を見る

- `py -m ai_shorts status`：状態ごとの一覧（物語CHECK待ち／動画づくり待ち／QA NG／動画CHECK待ち／投稿待ち／投稿済み／ボツ）。
- 「何をすればいい？」と聞かれたら、これを出して、ユーザーの番（CHECK待ち・投稿待ち）を先に伝える。

## 動画CHECK（ユーザーが判断する）

- `ready/<id>.mp4` を SendUserFile で渡し、スマホで見てもらう。**Claude が自分で OK にしない**（物語の承認と同じく、人の選別を通す方針。docs/policy.md）。
- OK と言われたら：`py -m ai_shorts approve-video <id> [<id> ...] --note "ユーザーのコメント"` → `upload/` に移る（投稿待ち）。
- ボツと言われたら、**理由と改善案をユーザーの言葉から聞き取って**記録する（聞いていなければ1回だけ聞く。改善案は Claude が案を出して確かめてもよい）。
  - 作り直す：`py -m ai_shorts reject-video <id> --reason "..." --idea "..." --remake` → 動画は `rejected/<id>-<n>.mp4`、物語は approved に残る。続けて直して（背景・config・本文）作り直す。本文を変えたら全文を見せて確認をもらう。
  - 物語ごとやめる：`... --drop` → 物語も `stories/rejected/` へ。

## 投稿（ユーザーが手動で）

- 自動投稿は作らない（CLAUDE.md の決まり 2、D-003）。Claude は投稿の準備と記録だけ。
- 投稿待ちの動画は `upload/<id>.mp4`、説明欄に貼る文は `upload/<id>.txt`。必要なら txt の中身をそのまま見せる。
- 「投稿した」と言われたら：`py -m ai_shorts posted <id> --platform youtube --url <URL> [--date 公開日]`
  - 予約投稿なら `--date` に公開日。URL がまだなければ省略してよい。あとで分かったら `stories/posted/<id>.json` の history のその行に `"url"` を足す。
  - 別の場所（Instagram など）にも上げたら、もう一度 `posted <id> --platform instagram ...`（記録が足されるだけ）。
- `posted/` の mp4・txt は消さない（投稿したものの原本。git には入らないので、バックアップはユーザーの判断）。

## 物語のボツ

- 物語CHECKでボツと言われたら：`py -m ai_shorts reject-story <id> --reason "..." --idea "..."`（draft か、動画がまだない approved から）。
- ボツの話を直したいと言われたら：`py -m ai_shorts revive-story <id> --note "..."` → draft に戻る。write-stories の手順で直して、もう一度物語CHECK。

## 改善案を見る・活かす

- `py -m ai_shorts ideas`：これまでのボツの理由と改善案（物語・動画別、日付順）。
- 新しく物語を書く前（write-stories）と動画を作る前（make-shorts）に読み、同じ理由でボツになりそうなものを避ける。
- 同じ理由が 3 回以上たまったら、仕組みで直せないか考える（story-guidelines.md・check_story.py の検査・config の既定値）。直したら decisions.md に書く。

## 書き方のこつ

- 理由は「何がだめだったか」を具体的に（×「微妙」 ○「オチが冒頭で読める」「2枚目の背景が明るすぎて字幕が読みにくい」）。
- 改善案は「次に何をするか」（○「ひねりを2段にする」「背景は夜の写真にする」「subs.outline を 6 に」）。
