"""投稿待ちの受け渡し（MiniPC で動かす）: タブレットで動画を保存し、タイトル・説明文をコピーする。

Python の標準ライブラリだけで動く（MiniPC に何も入れなくてよい）。LAN 専用。
データは --data のディレクトリに、このPCの `python -m ai_shorts share` が置く:

    data/<id>/video.mp4
    data/<id>/meta.json   {"id", "title", "description", "tags", "publish_at", "voice"}
    data/<id>/mark.json   タブレットで「投稿した」「ボツ」を送ると作られる（取り消すと消える）
        {"action": "posted", "date": "YYYY-MM-DD", "url": "..."}
        {"action": "rejected", "reason": "...", "idea": "...", "remake": true}
    次の `share` が mark.json を posted / reject-video の記録にして、data/<id> ごと消す。

    python3 server.py --port 8040 --data ~/projects/ai-shorts-share/data
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ID_RE = re.compile(r"[A-Za-z0-9_-]+")
CHUNK = 1 << 20


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """Range: bytes=a-b を (start, end)（end を含む）にする。読めない・範囲外なら None（全体を返す）。"""
    if not header:
        return None
    m = re.fullmatch(r"bytes=(\d*)-(\d*)", header.strip())
    if not m or (not m[1] and not m[2]) or size == 0:
        return None
    if m[1]:
        start = int(m[1])
        end = min(int(m[2]), size - 1) if m[2] else size - 1
    else:  # bytes=-N（末尾の N バイト）
        start, end = max(0, size - int(m[2])), size - 1
    if start > end or start >= size:
        return None
    return start, end


def load_items(data: Path) -> list[dict]:
    items = []
    for d in sorted(p for p in data.iterdir() if p.is_dir() and ID_RE.fullmatch(p.name)) if data.exists() else []:
        meta_path, video = d / "meta.json", d / "video.mp4"
        if not (meta_path.exists() and video.exists()):
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        mark_path = d / "mark.json"
        meta["mark"] = json.loads(mark_path.read_text(encoding="utf-8")) if mark_path.exists() else None
        meta["id"] = d.name
        meta["size_mb"] = round(video.stat().st_size / 1e6, 1)
        items.append(meta)
    return items


def _copy_block(label: str, text: str, key: str, rows: int) -> str:
    return (f'<div class="field"><div class="label"><span>{label}</span>'
            f'<button type="button" class="copy" data-target="{key}">コピー</button></div>'
            f'<textarea id="{key}" readonly rows="{rows}">{html.escape(text)}</textarea></div>')


def mark_label(mark: dict | None) -> str:
    if not mark:
        return "投稿待ち"
    if mark.get("action") == "posted":
        return f"投稿した {mark.get('date', '')}"
    return "ボツ（作り直す）" if mark.get("remake") else "ボツ（物語ごと）"


def _forms(i: str, publish_date: str) -> str:
    return f"""
  <div class="row">
    <button type="button" class="btn sub" data-open="p-{i}">投稿した</button>
    <button type="button" class="btn sub" data-open="r-{i}">ボツ</button>
  </div>
  <form class="mark" id="p-{i}" data-id="{i}" data-action="posted" hidden>
    <label>公開日（予約なら公開される日）<input type="date" name="date" required
      value="{html.escape(publish_date)}" data-default-today="{'0' if publish_date else '1'}"></label>
    <label>URL（あれば）<input type="url" name="url" placeholder="https://youtube.com/shorts/..."></label>
    <div class="row"><button class="btn">投稿したと記録する</button>
      <button type="button" class="btn sub" data-close="p-{i}">やめる</button></div>
  </form>
  <form class="mark" id="r-{i}" data-id="{i}" data-action="rejected" hidden>
    <label>理由（何がだめだったか）<textarea name="reason" rows="2" required></textarea></label>
    <label>改善案（次にどうするか。空なら Claude が案を出す）<textarea name="idea" rows="2"></textarea></label>
    <div class="choice">
      <label><input type="radio" name="remake" value="1" checked> 作り直す（物語は残す）</label>
      <label><input type="radio" name="remake" value="0"> 物語ごとボツ</label></div>
    <div class="row"><button class="btn">ボツにする</button>
      <button type="button" class="btn sub" data-close="r-{i}">やめる</button></div>
  </form>"""


def _mark_summary(i: str, mark: dict) -> str:
    if mark.get("action") == "posted":
        detail = html.escape(mark.get("url") or "URL なし")
    else:
        detail = (f"理由：{html.escape(mark.get('reason', ''))}<br>"
                  f"改善案：{html.escape(mark.get('idea') or '（空。Claude が案を出す）')}")
    return f"""
  <div class="summary">{detail}<div class="note">次の share でこのPCに記録され、ここから消えます。</div></div>
  <div class="row"><button type="button" class="btn sub" data-clear="{i}">取り消す</button></div>"""


def render_page(items: list[dict]) -> str:
    cards = []
    for it in items:
        i = html.escape(it["id"])
        mark = it.get("mark")
        when = ""
        if it.get("publish_at"):
            when = f'<div class="when">予約するなら <b>{html.escape(it["publish_at"])}</b></div>'
        publish_date = (it.get("publish_at") or "")[:10]
        tags = ", ".join(it.get("tags") or [])
        state = "" if not mark else (" posted" if mark.get("action") == "posted" else " rejected")
        cards.append(f"""
<section class="card{state}" id="c-{i}">
  <div class="head"><span class="id">{i}</span>
    <span class="badge">{html.escape(mark_label(mark))}</span></div>
  <video src="v/{i}.mp4" controls playsinline preload="metadata"></video>
  <div class="row">
    <a class="btn" href="dl/{i}.mp4" download="{i}.mp4">動画を保存（{it['size_mb']} MB）</a>
  </div>
  {when}
  {_mark_summary(i, mark) if mark else _forms(i, publish_date)}
  {_copy_block('タイトル', it.get('title', ''), f't-{i}', 1)}
  {_copy_block('説明文', it.get('description', ''), f'd-{i}', 8)}
  {_copy_block('タグ', tags, f'g-{i}', 1) if tags else ''}
</section>""")
    body = "".join(cards) or '<p class="empty">投稿待ちの動画はありません。</p>'
    return PAGE.replace("{{CARDS}}", body).replace("{{COUNT}}", str(len(items)))


PAGE = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>投稿待ち</title>
<style>
:root { --bg:#f6f5f2; --card:#fff; --fg:#222; --muted:#777; --line:#ddd; --accent:#c0392b; --ok:#2e7d32; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#161616; --card:#222; --fg:#eee; --muted:#999; --line:#3a3a3a; --accent:#e06c5f; --ok:#81c784; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:16px/1.6 system-ui, sans-serif; }
header { padding:16px; display:flex; justify-content:space-between; align-items:baseline; }
h1 { font-size:20px; margin:0; }
main { padding:0 16px 32px; display:grid; gap:16px; grid-template-columns:repeat(auto-fill, minmax(320px, 1fr)); }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px; }
.head { display:flex; justify-content:space-between; margin-bottom:8px; }
.id { font-family:ui-monospace, monospace; color:var(--muted); }
.badge { font-size:13px; padding:0 8px; border-radius:99px; border:1px solid var(--line); }
.posted .badge { color:var(--ok); border-color:var(--ok); }
.rejected .badge { color:var(--accent); border-color:var(--accent); }
.posted video, .rejected video { opacity:.5; }
form.mark { border:1px solid var(--line); border-radius:8px; padding:8px; margin:8px 0; }
form.mark label { display:block; font-size:14px; color:var(--muted); margin-bottom:8px; }
form.mark input[type=date], form.mark input[type=url] { width:100%; margin-top:4px; padding:8px; font-size:15px;
  border:1px solid var(--line); border-radius:6px; background:var(--bg); color:var(--fg); }
.choice label { color:var(--fg) !important; }
.summary { font-size:14px; border-left:3px solid var(--line); padding:4px 8px; margin:8px 0; word-break:break-all; }
.note { color:var(--muted); font-size:13px; margin-top:4px; }
video { width:100%; max-height:60vh; background:#000; border-radius:8px; aspect-ratio:9/16; }
.row { display:flex; gap:8px; margin:8px 0; flex-wrap:wrap; }
.btn { flex:1; text-align:center; padding:10px; border-radius:8px; border:0; font-size:15px;
  background:var(--accent); color:#fff; text-decoration:none; cursor:pointer; }
.btn.sub { background:transparent; color:var(--fg); border:1px solid var(--line); flex:0 0 auto; }
.when { font-size:14px; color:var(--muted); margin:4px 0 8px; }
.field { margin-top:8px; }
.label { display:flex; justify-content:space-between; align-items:center; font-size:14px; color:var(--muted); }
.copy { padding:4px 12px; border-radius:6px; border:1px solid var(--line); background:transparent; color:var(--fg); font-size:14px; }
.copy.ok { color:var(--ok); border-color:var(--ok); }
textarea { width:100%; margin-top:4px; padding:8px; border:1px solid var(--line); border-radius:6px;
  background:var(--bg); color:var(--fg); font:15px/1.5 system-ui, sans-serif; resize:vertical; }
.empty { color:var(--muted); }
</style></head>
<body>
<header><h1>投稿待ち</h1><span class="id">{{COUNT}} 本</span></header>
<main>{{CARDS}}</main>
<script>
function copyText(el) {
  // http（LAN）では navigator.clipboard が使えないので、選択してコピーする方法も使う
  if (window.isSecureContext && navigator.clipboard) return navigator.clipboard.writeText(el.value);
  el.focus(); el.select(); el.setSelectionRange(0, el.value.length);
  const ok = document.execCommand('copy');
  return ok ? Promise.resolve() : Promise.reject();
}
document.querySelectorAll('.copy').forEach(b => b.addEventListener('click', () => {
  const el = document.getElementById(b.dataset.target);
  copyText(el).then(() => { b.textContent = 'コピーしました'; b.classList.add('ok'); },
                    () => { b.textContent = '選択したので手でコピー'; });
  setTimeout(() => { b.textContent = 'コピー'; b.classList.remove('ok'); }, 2000);
}));
async function sendMark(id, body) {
  const r = await fetch('api/mark/' + id, { method: 'POST',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (r.ok) location.reload(); else alert('送れませんでした：' + await r.text());
}
const today = () => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 10); };
document.querySelectorAll('[data-default-today="1"]').forEach(el => { el.value = today(); });
document.querySelectorAll('[data-open]').forEach(b => b.addEventListener('click', () => {
  const card = b.closest('.card');
  card.querySelectorAll('form.mark').forEach(f => { f.hidden = f.id !== b.dataset.open; });
}));
document.querySelectorAll('[data-close]').forEach(b => b.addEventListener('click', () => {
  document.getElementById(b.dataset.close).hidden = true;
}));
document.querySelectorAll('form.mark').forEach(f => f.addEventListener('submit', e => {
  e.preventDefault();
  const v = Object.fromEntries(new FormData(f));
  const body = f.dataset.action === 'posted'
    ? { action: 'posted', date: v.date, url: (v.url || '').trim() }
    : { action: 'rejected', reason: v.reason.trim(), idea: (v.idea || '').trim(), remake: v.remake === '1' };
  sendMark(f.dataset.id, body);
}));
document.querySelectorAll('[data-clear]').forEach(b => b.addEventListener('click', () => {
  if (confirm('取り消しますか？')) sendMark(b.dataset.clear, { action: null });
}));
</script>
</body></html>
"""


class Handler(BaseHTTPRequestHandler):
    data: Path  # make_server で設定

    def log_message(self, fmt: str, *args) -> None:  # 動画の分割読み込みでログが埋まるので、エラーだけ出す
        if args and str(args[1] if len(args) > 1 else "").startswith(("4", "5")):
            super().log_message(fmt, *args)

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _video(self, story_id: str, download: bool) -> None:
        path = self.data / story_id / "video.mp4"
        if not path.exists():
            return self._send(404, b"not found", "text/plain")
        size = path.stat().st_size
        rng = None if download else parse_range(self.headers.get("Range"), size)
        start, end = rng or (0, size - 1)
        self.send_response(HTTPStatus.PARTIAL_CONTENT if rng else HTTPStatus.OK)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if rng:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{story_id}.mp4"')
        self.end_headers()
        if self.command == "HEAD":
            return
        with path.open("rb") as f:
            f.seek(start)
            left = end - start + 1
            try:
                while left > 0:
                    chunk = f.read(min(CHUNK, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass  # 再生位置を飛ばすとブラウザが途中で切る

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/":
            return self._send(200, render_page(load_items(self.data)).encode("utf-8"), "text/html; charset=utf-8")
        m = re.fullmatch(r"/(v|dl)/([A-Za-z0-9_-]+)\.mp4", path)
        if m:
            return self._video(m[2], download=m[1] == "dl")
        self._send(404, b"not found", "text/plain")

    do_HEAD = do_GET

    def do_POST(self) -> None:
        m = re.fullmatch(r"/api/mark/([A-Za-z0-9_-]+)", self.path)
        d = self.data / m[1] if m else None
        if not d or not d.is_dir():
            return self._send(404, b"not found", "text/plain")
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            mark = validate_mark(body)
        except (ValueError, AttributeError) as e:
            return self._send(400, str(e).encode("utf-8"), "text/plain; charset=utf-8")
        path = d / "mark.json"
        if mark is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(json.dumps(mark, ensure_ascii=False), encoding="utf-8")
        self._send(200, b'{"ok":true}', "application/json")


def validate_mark(body: dict) -> dict | None:
    """タブレットから来た印を確かめて、mark.json の中身にする。action が空なら取り消し（None）。"""
    action = body.get("action")
    if not action:
        return None
    if action == "posted":
        date = str(body.get("date", "")).strip()
        dt.date.fromisoformat(date)  # 形が違えば ValueError
        url = str(body.get("url", "")).strip()
        if url and not url.startswith(("https://", "http://")):
            raise ValueError("URL は https:// から書いてください")
        return {"action": "posted", "date": date, "url": url}
    if action == "rejected":
        reason = str(body.get("reason", "")).strip()
        if not reason:
            raise ValueError("ボツの理由を書いてください")
        return {"action": "rejected", "reason": reason, "idea": str(body.get("idea", "")).strip(),
                "remake": bool(body.get("remake")), "date": dt.date.today().isoformat()}
    raise ValueError(f"action が不明です: {action}")


def make_server(port: int, data: Path) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"data": data})
    return ThreadingHTTPServer(("0.0.0.0", port), handler)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8040)
    ap.add_argument("--data", type=Path, default=Path(__file__).with_name("data"))
    args = ap.parse_args()
    args.data.mkdir(parents=True, exist_ok=True)
    print(f"http://0.0.0.0:{args.port}/  data={args.data}", flush=True)
    make_server(args.port, args.data.resolve()).serve_forever()


if __name__ == "__main__":
    main()
