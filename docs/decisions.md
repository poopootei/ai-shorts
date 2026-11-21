# 決定事項の記録

新しい決定は下に追記する。形式：ID / 日付 / 決定 / 理由。

## D-001 2026-11-17 主な収益源は自作BGMの Content ID
- ショート動画の広告収益は狙わない。TuneCore Japan 経由で BGM を Content ID に登録し、自分の動画にも申し立てが付く形にする。

## D-002 2026-11-17 動画は59秒以下
- Content ID の申し立てが付いた1分超のショートはブロックされるため。

## D-003 2026-11-17 自動化は mp4 まで、投稿は手動（→ D-015 で見直し）
- YouTube Data API は、審査を通っていないプロジェクトから投稿すると非公開に固定され、異議申し立てもできないため。予約投稿で運用する。

## D-004 2026-11-17 BGM の作曲は人がする
- TuneCore Japan は生成AI楽曲を Content ID に登録できない。作曲（メロディ・和音・構成）はユーザー、Claude はシンセエンジンとレンダリングを担当する。SoundFont やサンプル素材は使わない。

## D-005 2026-11-17 すべてローカル・無料
- VOICEVOX、ComfyUI、ffmpeg をローカルで使う。物語は Claude Code セッション内で生成する。

## D-006 2026-11-17 物語は 250〜280字
- sample-001（214字・11文）を冥鳴ひまり・話速0.92で合成したところ、読み上げ 37.7秒（5.7字/秒）＋無音・間 7.6秒 ＝ 45.3秒だった。
- 当初の 300〜350字では、330字で約68秒、話速を上限の1.05にしても約60秒になり、58秒に収まらない。話速0.92のまま収まる 250〜280字に変える。
- 話者や話速を変えたら、この字数を測り直す。

## D-007 2026-11-17 VOICEVOX はエンジンだけを tools/ に置く
- アプリはインストールせず、GitHub の voicevox_engine（0.26.2、CPU版の .vvpp）を `tools/voicevox_engine/` に展開する（git 管理外）。環境をきれいに保つため。
- CPU版にしたのは、GPU の VRAM（8GB）を ComfyUI に残すため。

## D-008 2026-11-17 ComfyUI ができるまで、背景は Openverse の CC0 / PDM 写真
- `scripts/fetch_stock_images.py` で Openverse（API キー不要）を検索し、ライセンスが CC0 かパブリックドメイン（PDM）のものだけを使う。商用利用でき、クレジット表記も不要。出典は `work/{id}/images.json` に残し、説明文にも書く。
- 外部への HTTP 通信を伴うが、ユーザーの了承済み（「ネットからフリー素材を拾ってきていい」）。パイプライン本体（`python -m ai_shorts`）には入れず、scripts/ の単発ツールにとどめる。
- 絵柄がそろわないので、シリーズとして出す前に ComfyUI の生成画像へ切り替える（policy.md の「絵柄とシリーズとしての一貫性」）。

## D-009 2026-11-17 字幕のフォントは Noto Serif JP Medium（OFL）
- notofonts/noto-cjk の SubsetOTF を `assets/fonts/` に置く。ライセンス文は `assets/fonts/licenses/`（fontsdir に置くと libass がフォントとして読もうとするため分けた）。
- libass はファミリー名で探すので、config の font_name は "Noto Serif JP Medium"。

## D-010 2026-11-17 声は冥鳴ひまり（ノーマル）、話速0.92・抑揚1.0
- 「声が不自然」との指摘を受けて原因を直した：かぎかっこの前後に VOICEVOX が間を入れる（読み上げる文からかぎかっこを外す）、アクセントの誤り（assets/voicevox/user_dict.yaml）、文頭の無音を0にしていた（エンジンの既定0.1秒に戻す）。
- 修正後に、ひまり 0.92 / ひまり 1.0・抑揚1.2 / No.7 読み聞かせ / 青山龍星 しっとり を聞き比べ、ひまり 0.92・抑揚1.0 に決めた。
- 話者の利用規約の確認はまだ（未決定の項目に残す）。→ D-011 で置き換え。

## D-011 2026-11-19 声は COEIROINK を中心に、AivisSpeech の阿井田 茂も使う。物語ごとに選ぶ
- 「機械音声っぽさが残る」「雰囲気に合った声、男性の声も」との要望。参考にした動画（COEIROINK 使用）を受けて、無料・ローカルの COEIROINK v2.13.0 と AivisSpeech Engine 1.2.0 を試した。
- 11種類を聞き比べ、COEIROINK（おふとんP・つくよみちゃん）は全体的に良い、AivisSpeech は阿井田 茂のみ良い、VOICEVOX の冥鳴ひまりと AivisSpeech のほかの声は使わない、と決めた。
- COEIROINK は 小部屋 を「しょうへや」と読んだが、/v1/set_dictionary で直せることを確認した。辞書は全エンジン共通の assets/tts/user_dict.yaml。
- 声は config.yaml の voices に登録し、物語 JSON の "voice" で選ぶ。クレジットは声ごとの credit を説明文と画面に出す。
- 規約（2026-11-19 に確認）：
  - おふとんP・つくよみちゃん（COEIROINK）：個人・法人の商用利用可。クレジット必須（「COEIROINK:おふとんP」など）。
  - 阿井田 茂（AivisHub、ACML 1.0）：個人・法人の商用利用可。クレジットは任意だが「AivisSpeech:阿井田 茂」と出す。
- 長さ：話速 1.0 の COEIROINK / AivisSpeech は、冥鳴ひまり 0.92 より約1割速い（250〜280字で 46〜48秒）。字数の目安（D-006）は当面そのままにし、本数が増えたら測り直す。

## D-012 2026-11-20 CHECK を2回通し、投稿とボツを記録する
- 流れ：物語 → 物語CHECK（人）→ 動画 → 動画CHECK（人）→ 投稿（人）。動画にも人の確認を必ず入れる（Claude が自分で OK にしない）。
- 状態はフォルダで表す：`stories/{draft,approved,posted,rejected}/`、動画は `ready/`（CHECK待ち）→ `upload/`（投稿待ち）→ `posted/`、ボツ動画は `rejected/{id}-{n}.mp4`。
- 経緯（承認・ボツ・投稿）は物語 JSON の `history` に残す。git で追えるようにするため、別の台帳ファイルは作らない。mp4 は従来どおり git に入れない。
- ボツは消さず、理由と改善案を必ず書く（`python -m ai_shorts ideas` で一覧）。物語を書く前・動画を作る前に読み返し、同じ理由のボツが続いたら guidelines・検査・config を直す。
- 投稿は手動のまま（D-003）。`posted` は投稿したことの記録だけで、外部への通信はしない。（D-015 で、予約投稿と記録をまとめて行う `upload` を足した）

## D-013 2026-11-20 冒頭の hook は帯で囲み、本文より先に単独で出す
- 「冒頭でタイトルと本文の区別がつかず、ごちゃっとしている」との指摘。hook（冒頭2秒）と最初の本文の字幕が、同じ白文字・黒縁で同時に出ていた。
- 見本（いまのまま／先に出すだけ／帯だけ／帯＋先に）を比べ、ユーザーが「帯＋先に」に決めた。
- hook は半透明の黒い帯で囲み（`subs.hook_box`、濃さ 0.75）、画面の 40% の高さに出す。声の前の無音（`tts.pre_silence`）を 1.0 → 2.0 秒にし、hook は最初の文が始まるまでに消す（`subs.hook_alone`）。
- 動画は約1秒長くなる。いまの物語は 43〜49 秒なので、59 秒の上限には余裕がある。

## D-014 2026-11-20 このリポジトリでチャンネルの運用全般を扱う
- 対象は YouTube チャンネル「ショートショートの世界へ」。動画づくりに加えて、説明文・プロフィール・投稿の方針と記録などのマネジメントもここで扱う。情報は docs/channel.md。
- Claude は案と記録まで。YouTube Studio での変更と投稿はユーザーが手で行う（D-003）。（投稿は D-015 で `upload` に変えた。Studio での設定の変更は引き続きユーザーが行う）

## D-015 2026-11-20 YouTube への投稿を API の予約投稿にする（D-003 の見直し）
- 2026-11-02 から、審査を通っていない API プロジェクトから上げた動画も、非公開に固定されなくなった（YouTube Data API の改訂履歴と videos.insert の説明で確認）。D-003 の理由がなくなったので、ユーザーが自動化に決めた。
- `python -m ai_shorts upload` で、動画CHECK に通った `upload/` の動画を非公開で上げ、`publishAt` で予約公開する。公開は 1 日 1 本、時刻は `youtube.publish_time`。最初の公開日は、これまでの YouTube の公開日の翌日。上げたら `posted` の記録（URL・公開日）まで行う。
- 人の確認は減らさない。物語CHECK・動画CHECK はそのまま。`upload` を実行するのはユーザーが「投稿して」と言ったときだけで、Claude はまず `--dry-run` で公開の予定を見せて了承を得る。定期実行で勝手に投稿する仕組みは作らない。
- API は YouTube Data API v3（無料。アップロードは 1 日 100 回の枠）。権限は `youtube.upload` だけ。認証情報は `secrets/`（git 管理外）。依存に google-api-python-client と google-auth-oauthlib を足した（ユーザーが了承）。
- OAuth の同意画面は「本番」にする（「テスト」のままだとログインが 7 日で切れる）。自分だけで使うので Google の確認は申し込まない。ログインのとき「未確認のアプリ」と出る。
- 「改変または合成されたコンテンツ」の申告（`containsSyntheticMedia`）は false。合成音声で朗読しているが、実在の人や出来事に見えるものではないため。変えるなら `youtube.contains_synthetic_media`。
- YouTube Studio から手で上げることもできる。そのときは従来どおり `posted` で記録する。

## D-016 2026-11-21 タブレットから上げるために、投稿待ちを MiniPC で受け渡す
- ユーザーがタブレットの YouTube アプリから手で上げたいので、`upload/` の動画とタイトル・説明文・タグを LAN の MiniPC（`lenovo`、Ubuntu）に置き、タブレットのブラウザで動画を保存し、文をコピーできるようにした。Google ドライブは使わない（このPCにドライブのアプリがなく、API を足すと権限が増えるため）。
- `python -m ai_shorts share` で送る。送るのは ssh だけ（`~/.ssh/config` の Host 名、`share.host`）。同じ大きさの動画は送り直さず、`upload/` にないもの（投稿済み・ボツ）は MiniPC から消す。
- MiniPC の Web アプリ（`share_app/server.py`）は Python の標準ライブラリだけで書き、MiniPC に何も入れない。ほかのアプリと同じく `~/projects/ai-shorts-share` に置き、`systemd --user`（`ai-shorts-share.service`）でポート 8040 に出す。LAN 専用で、ログインはない。
- タブレットで「投稿した」（公開日・URL）か「ボツ」（理由・改善案・作り直すか物語ごとか）を送ると MiniPC に印が残り、次の `share` がこのPCの記録（`posted` / `reject-video` と同じ）にして、MiniPC から消す。判断して入力するのはユーザーなので、人が決める方針と合う。`share` までは取り消せる。
  - ボツで改善案が空のものは記録しない。`share` が「要対応」と出すので、Claude が改善案を出してユーザーに確かめ、`reject-video` で記録する（ボツの理由と改善案を必ず残す決まりのため）。
- 投稿するかどうかは人が決めるまま（CLAUDE.md の2）。`share` は外部（YouTube）に何も送らない。

## 未決定
- [ ] おふとんPの追加スタイル（ナレーション・どくはく・ホラーなど。1パック 1.39GB）を入れるか
- [ ] 画像生成モデルとそのライセンス
- [ ] 絵柄（assets/styles/）
- [ ] BGM の音量（Content ID 検出テストの結果で決める）
- [ ] BGM をショートに焼き込むか、アプリで「サウンド」として付けるか（API では付けられない。検証テストで TuneCore に収益が入るかを見て決める。bgm.md）
- [ ] TuneCore のプラン
