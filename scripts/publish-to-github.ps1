# Publishes this folder to https://github.com/<owner>/<repo>
# Usage: right-click "Publish to GitHub.bat" -> Run, or:
#   powershell -ExecutionPolicy Bypass -File scripts\publish-to-github.ps1 -Owner aicareerversestartup-glitch -Repo ai-job-hunter
param(
  [string]$Owner = "aicareerversestartup-glitch",
  [string]$Repo = "ai-job-hunter",
  [ValidateSet("public", "private")][string]$Visibility = "public"
)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  Write-Host "Git is not installed. Install it from https://git-scm.com/download/win, then run this again." -ForegroundColor Yellow
  exit 1
}

if (-not (Test-Path .git)) {
  git init -b main | Out-Null
}
if (-not (git config user.name))  { git config user.name  $Owner }
if (-not (git config user.email)) { git config user.email "$Owner@users.noreply.github.com" }

git add -A
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) { git commit -m "AI Job Hunter: international job search with truthful, country-specific CVs" | Out-Null }

$url = "https://github.com/$Owner/$Repo.git"
if (Get-Command gh -ErrorAction SilentlyContinue) {
  gh auth status 2>$null | Out-Null
  if ($LASTEXITCODE -ne 0) { gh auth login --web }
  gh repo view "$Owner/$Repo" 2>$null | Out-Null
  if ($LASTEXITCODE -ne 0) {
    gh repo create "$Owner/$Repo" --$Visibility --description "Find jobs abroad that fit your real experience and apply with a truthful CV in each country's format. FastAPI + React + Capacitor." | Out-Null
  }
} else {
  Write-Host ""
  Write-Host "1) Open https://github.com/new and create a $Visibility repository named '$Repo' (leave README unticked)." -ForegroundColor Cyan
  Read-Host "2) Press Enter here when it's created"
}

if (git remote | Select-String -Quiet "^origin$") { git remote set-url origin $url } else { git remote add origin $url }
git push -u origin main
if ($LASTEXITCODE -eq 0) {
  Write-Host "Done: https://github.com/$Owner/$Repo" -ForegroundColor Green
  Start-Process "https://github.com/$Owner/$Repo"
}
