# Phase 15 Docker smoke test for SilentSignal (PowerShell, repo convention:
# see backend/run_backend.ps1). Verifies a WORKING demo, not just started
# containers:
#
#   1. docker compose up -d --build
#   2. Postgres container healthy
#   3. Backend /api/health responds (waits for seed/migrations)
#   4. Frontend serves HTTP 200
#   5. POST /api/demo/reset succeeds
#   6. GET /api/dashboard/summary returns non-empty data
#
# Exits 0 on success, non-zero on any failure. Containers are left running
# for inspection; pass -Down to tear them down afterwards.
#
# Prerequisites: Docker Engine + Compose v2. No local Python/Node/Postgres
# needed. First run builds images (several minutes on a clean machine).

param(
    [string]$BackendUrl = "http://localhost:8000",
    [string]$FrontendUrl = "http://localhost:5173",
    [int]$TimeoutSeconds = 600,
    [switch]$Down
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

function Fail([string]$msg) {
    Write-Host "SMOKE FAIL: $msg" -ForegroundColor Red
    exit 1
}

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)

Write-Host "== docker compose up -d --build =="
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { Fail "docker compose up failed" }

function Wait-Until([string]$label, [scriptblock]$probe) {
    Write-Host "== waiting: $label =="
    while ((Get-Date) -lt $deadline) {
        try {
            if (& $probe) { Write-Host "OK: $label" -ForegroundColor Green; return }
        } catch { }
        Start-Sleep -Seconds 5
    }
    Fail "timed out waiting for: $label"
}

Wait-Until "postgres healthy" {
    $id = (docker compose ps -q postgres).Trim()
    if (-not $id) { return $false }
    (docker inspect --format '{{.State.Health.Status}}' $id).Trim() -eq "healthy"
}

Wait-Until "backend /api/health" {
    (Invoke-RestMethod -Uri "$BackendUrl/api/health" -TimeoutSec 5).status -eq "ok"
}

Wait-Until "frontend HTTP 200" {
    (Invoke-WebRequest -Uri $FrontendUrl -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200
}

Write-Host "== POST /api/demo/reset =="
try {
    $reset = Invoke-RestMethod -Uri "$BackendUrl/api/demo/reset" -Method Post -TimeoutSec 600
} catch { Fail "POST /api/demo/reset failed: $($_.Exception.Message)" }
if ($reset.status -ne "ok" -or $reset.assets -lt 1) { Fail "demo reset bad response: $($reset | ConvertTo-Json -Compress)" }
Write-Host "OK: demo reset (assets=$($reset.assets))" -ForegroundColor Green

Write-Host "== GET /api/dashboard/summary =="
try {
    $summary = Invoke-RestMethod -Uri "$BackendUrl/api/dashboard/summary" -TimeoutSec 30
} catch { Fail "GET /api/dashboard/summary failed: $($_.Exception.Message)" }
if ($summary.total_assets -lt 1) { Fail "dashboard summary empty: $($summary | ConvertTo-Json -Compress)" }
Write-Host "OK: dashboard summary (total_assets=$($summary.total_assets), alerts=$($summary.total_alerts))" -ForegroundColor Green

Write-Host "== TEE mode =="
try {
    $tee = Invoke-RestMethod -Uri "$BackendUrl/api/security/tee-status" -TimeoutSec 15
    Write-Host "tee-status mode=$($tee.mode) healthy=$($tee.healthy)"
    if ($tee.mode -ne "demo") { Fail "Compose must default to TEE_MODE=demo, got $($tee.mode)" }
} catch { Fail "tee-status failed: $($_.Exception.Message)" }

Write-Host "SMOKE PASS" -ForegroundColor Green

if ($Down) {
    Write-Host "== docker compose down =="
    docker compose down
}
