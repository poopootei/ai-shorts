---
name: make-shorts
description: ai-shorts で朗読ショート動画を作る全体の流れ（物語 → 検査・承認 → 背景 → 声 → 合成 → QA → 動画CHECK → 投稿待ち）。「動画を作って」「〇本作って」「ショートを作りたい」「試しに動画を」「作り直して」「通しで」など、動画を新しく作る・まとめて作る・作り直す依頼では、必ず最初にこのスキルを使う。物語だけ・背景だけ・声だけの依頼は、それぞれ write-stories / pick-backgrounds / manage-voices を使う。
---

# 朗読ショートを作る

`<ch>` はチャンネル名（CLAUDE.md の「チャンネル」）。`stories/`・`work/`・`upload/`・`config.yaml` などのパスは、チャンネルのフォルダ `channels/<ch>/` から見たもの。

手順の詳細と根拠は `docs/runbook.md`。ここは Claude が実行するときの段取り。
作業のルートは `D:\prj\ai-shorts`、Python は `.venv\Scripts\python`（以下 `py`）。

## 段取り

1. **計画を立てる**：何本・どんなジャンルか、既存の物語を使うか新しく書くかを依頼から決める。曖昧なら本数とジャンルの希望だけ聞く。
   - `py -m ai_shorts -c <ch> status` で、作りかけ（動画づくり待ち・QA NG）や CHECK 待ちが残っていないか見る。
   - `py -m ai_shorts -c <ch> ideas` で、これまでのボツの理由と改善案を読み、同じ失敗を避ける。
2. **エンジンを確かめる**：`py scripts/tts_status.py -c <ch>`。止まっていれば起動する（runbook 2）。セッションをまたぐと止まっているのが普通。
3. **物語**：新しく書くなら write-stories スキルに従って下書き → 検査 → 自分で確認点を見て直す → `approve_story.py` で承認し、そのまま背景・合成へ進む。物語CHECK はしない（D-018）。全文をユーザーに見せて待たない。
4. **映像の分かれ道**：物語 JSON の `visual` を見る（`status` では題に［3D］が付く）。
   - 書いていない（静止画）：pick-backgrounds スキルに従って、段落ごとに1枚を ID で取る。候補シートは自分で見て選び、外れ（広告・ロゴ・雰囲気違い）は除く。
   - `"3d"`：背景画像は選ばない。手順5の `all` が qa の前で止まるので、そのあと下の「3D の舞台」に進む。
5. **合成**：`py -m ai_shorts -c <ch> all --id <id>`（複数なら id ごと）。止まったらエラーの文面どおりに直す（多いのは「長すぎる」→ 本文を短くしてユーザーに確認、「接続できない」→ エンジン起動）。
   - **3D の舞台**（visual: 3d。runbook 3-3b、D-027・D-028）：
     1. `scripts/blender/<id>.py` を書く。部品は `scripts/blender/kit.py`（人形・座る・立つ・歩く・手の行き先と向き・物を持つ・文字・家具・光）。既存の舞台（20261124-002 など）を手本にする。段取りは timing.json の文の時刻に合わせる。
     2. 下見：`py scripts/render_3d.py -c <ch> <id> --stills <秒,...> --scale 40` → `work/<id>/3d/still_*.png` を自分で見る。人形の向き（背中ばかり写っていないか）、ひじ・ひざの曲がる向き、手が物にめり込んでいないか、小物が手で隠れていないか、文字の大きさ。直してまた下見。
     3. 全編：`py scripts/render_3d.py -c <ch> <id>`（8〜12 分。run_in_background で）→ 書き出したら数秒おきのコマを並べて見る。
     4. `py scripts/render_3d.py -c <ch> <id> --adopt` → `py -m ai_shorts -c <ch> qa --id <id>`。
     - Blender の場所は config の `blender.exe`。なければ `--blender D:\blender\blender.exe`。
     - 何本もあるときは、全部の舞台を下見まで済ませてから、全編をまとめて書き出す（書き出しの待ち時間に次の舞台を書く）。
6. **確認**：qa が全部 OK か見る。`py scripts/preview_video.py -c <ch> <id>` のコマ画像を自分で見て、字幕・背景・クレジットの崩れがないか確かめる。数字の検査だけで終わらせない（QA は見た目の違和感までは拾えない）。
   - 字幕の切れ目も全部読む：`py -c "import json;d=json.load(open('work/<id>/subs.json',encoding='utf-8'));print(' / '.join('｜'.join(e['lines']) for e in d['events']))"`。言葉の途中（生き｜物）や2字だけの行（うまって｜いる）があれば `src/ai_shorts/subs.py` を直し、tests/test_subs.py に例を足してから `subs`・`render`・`qa` をやり直す。
7. **動画CHECK を頼む**：`ready/<id>.mp4` をユーザーに送り（SendUserFile）、表で「タイトル・長さ・声」をまとめて、OK かボツかを聞く。説明文は `ready/<id>.txt`。
8. **結果を記録する**：review-and-post スキルに従う。OK → `approve-video`（upload/ へ、投稿待ち）。ボツ → 理由と改善案を聞いて `reject-video`（作り直すなら `--remake`）。**Claude が自分で OK にしない。**
9. **残っていることを伝える**：BGM なし、など。投稿はユーザーが「投稿して」と言ったときだけ、review-and-post スキルの手順で `upload` する（予定を見せて了承を得てから）。

## 守ること（理由つき）

- **動画を OK にするのはユーザーだけ**：物語は Claude が検査して承認するが（D-018）、動画CHECK は人が通す。`approve-video` はユーザーが OK と言ったときだけ。
- **59 秒以下**：Content ID の申し立てが付いた1分超のショートはブロックされる。qa の「長さ」が NG なら出さない。
- **ダウンロードは了承を得てから**：エンジン・声の追加は数百 MB〜1GB 超。何を・どこから・何 MB かを伝えてから。
- **有料 API は使わない。頼まれていない投稿はしない**（CLAUDE.md）。
- **方針に関わる判断**（新しい声、新しい画像の出どころ、字数の目安の変更など）は `docs/decisions.md` に追記する。

## 渡すときの書き方（例）

| ファイル | タイトル | 長さ | 声 |
|---|---|---|---|
| ready/20261120-001.mp4 | 〇〇 | 48.2秒 | COEIROINK:おふとんP |

そのあとに「まだのこと」（BGM、スマホ確認など）を短く。
