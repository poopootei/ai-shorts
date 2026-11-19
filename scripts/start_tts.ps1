# 音声合成エンジンを起動する（それぞれ別のウィンドウで動く。止めるときはそのウィンドウを閉じる）。
#   COEIROINK   → http://127.0.0.1:50032
#   AivisSpeech → http://127.0.0.1:10101（エラー情報の外部送信は切る）
# 使い方: powershell -ExecutionPolicy Bypass -File scripts\start_tts.ps1
$root = Split-Path -Parent $PSScriptRoot
$coe = Join-Path $root "tools\coeiroink\engine\engine.exe"
$aivis = Join-Path $root "tools\aivisspeech_engine\run.exe"
foreach ($p in @($coe, $aivis)) {
    if (-not (Test-Path $p)) { Write-Error "$p がありません。README の「音声合成エンジン」の手順で展開してください。"; exit 1 }
}
Start-Process -FilePath $coe -WorkingDirectory (Split-Path $coe)
Start-Process -FilePath $aivis -ArgumentList "--host", "127.0.0.1", "--port", "10101", "--disable_sentry"
