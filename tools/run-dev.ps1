# Starts the local dev stack in three windows: API (:8000), job worker, web app (:5173).
#   -NoLogin      one-tap demo mode without phone + PIN (AUTH_DISABLED=1; also set VITE_NO_LOGIN=1 in apps/web/.env.local)
#   -SimSpeech    use the simulated speech backend instead of the real Hindi wav2vec2 model
# Usage (from the repo root):  powershell -ExecutionPolicy Bypass -File tools\run-dev.ps1
param([switch]$NoLogin, [switch]$SimSpeech)

$root = Split-Path -Parent $PSScriptRoot
$api = Join-Path $root 'services\api'
$web = Join-Path $root 'apps\web'
$py = Join-Path $api '.venv\Scripts\python.exe'

$envs = @()
if ($NoLogin) { $envs += '$env:AUTH_DISABLED="1"' }
if (-not $SimSpeech) { $envs += '$env:SPEECH_BACKEND="wav2vec2"'; $envs += '$env:HF_HUB_OFFLINE="1"' }
$prefix = ($envs -join '; ')
if ($prefix) { $prefix += '; ' }

Start-Process powershell -WorkingDirectory $api -ArgumentList '-NoExit', '-Command', "$prefix& '$py' -m uvicorn app.main:app --port 8000"
Start-Sleep -Seconds 8  # let the API create/upgrade the database before the worker starts polling it
Start-Process powershell -WorkingDirectory $api -ArgumentList '-NoExit', '-Command', "$prefix& '$py' -m app.jobs.worker --scheduler"
Start-Process powershell -WorkingDirectory $web -ArgumentList '-NoExit', '-Command', 'npm run dev -- --port 5173'
Write-Host 'Open http://localhost:5173'
