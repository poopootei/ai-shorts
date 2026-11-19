---
name: pick-backgrounds
description: ai-shorts の動画の背景画像を、Openverse の CC0 / パブリックドメイン写真から段落ごとに選んで work/{id}/img_N.png に置く。「背景を選んで」「画像を差し替えて」「この画像は合ってない」「背景を探して」など、背景画像の選定・差し替えでは必ずこのスキルを使う（ComfyUI での生成ができるまでの仮の方法。docs/decisions.md D-008）。
---

# 背景画像を選ぶ

Python は `.venv\Scripts\python`（以下 `py`）。画像は CC0 か PDM だけ（スクリプトがそれ以外を弾く）。

## 手順

1. 段落ごとの場面を決める：物語 JSON の `image_prompts` と `notes` の検索語候補を見る。
2. 候補シートを作る：
   `py scripts/preview_backgrounds.py --name <id> "検索語1" "検索語2" "検索語3"`
   - 1行 = 1検索語、上位4枚。端末に `検索語 [列] ID ライセンス 出典: タイトル` が出る。
   - `work/_previews/<id>_sheet.png` を Read で**自分の目で見て**選ぶ。タイトルだけで選ばない（「elevator」で花の図版が出るなど、タイトルと中身がずれる）。
3. 合うものがなければ検索語を変えて 2 をくり返す。
   - 英語の短い語（2〜3語）が当たりやすい。具体物（"radio telescope night"）か雰囲気（"empty office", "milky way"）。
   - 屋内の細かい場面は見つかりにくい。物語の雰囲気に合う別の絵（夜空、古い部屋など）で代えてよい。
4. ID で取る（検索の順番は毎回変わるので、--skip ではなく ID を使う）：
   `py scripts/fetch_stock_images.py --id <id> --query "id:<ID1>" --query "id:<ID2>" --query "id:<ID3>"`
   - 1枚だけ差し替えるときも全段落分を渡す。残す画像の ID は `work/<id>/images.json` の `openverse_id`。
5. 取れた3枚を並べて確かめる（ffmpeg で `hstack` したものを Read で見る）。合っていなければ 4 をやり直す。
6. 動画に反映するには `py -m ai_shorts render --id <id>` と `qa`（tts と subs は不要）。

## 選ぶ基準

- 物語の場面・雰囲気に合う。段落の切り替えで違和感がない。
- 避ける：広告・本の宣伝・ブランドロゴが目立つもの、実在の人物の顔が主役のもの、文字が多い図版。
- 縦長で 900px 以上（スクリプトが絞り込む）。横長は 9:16 に中央で切り抜かれるので、主役が中央にあるものを選ぶ。
- Openverse が 504 を返したら、スクリプトが数回やり直す。続くなら少し待つ。

## 記録

出典とライセンスは `work/<id>/images.json` に自動で残り、qa が説明文（`ready/<id>.txt`）に「背景画像：CC0（出典）」として書く。
