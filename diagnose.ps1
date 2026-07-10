# =====================================================================
# diagnose.ps1 - Claude Code Windows UTF-8 Kit
# 環境診断(読み取り専用・このスクリプトは何も変更しません)
# Read-only diagnostics. This script changes NOTHING on your system.
# =====================================================================
$ErrorActionPreference = 'SilentlyContinue'

Write-Host ""
Write-Host "==== Claude Code Windows UTF-8 Kit / 環境診断 ====" -ForegroundColor Cyan
Write-Host "(read-only: 何も変更しません)" -ForegroundColor DarkGray
Write-Host ""

$rows = @()
function Add-Row($item, $recommend, $current, $ok) {
    $verdict = 'OK'
    if (-not $ok) { $verdict = '要検討 (check)' }
    $script:rows += [PSCustomObject]@{
        Item        = $item
        Recommended = $recommend
        Current     = $current
        Verdict     = $verdict
    }
}

# --- 1. OS / PowerShell バージョン ---
$psv = $PSVersionTable.PSVersion.ToString()
Add-Row 'PowerShell version' '5.1 or 7.x' $psv $true

# --- 2. コードページ ---
$cpRaw = (chcp)
$cp = ($cpRaw -replace '[^0-9]', '')
Add-Row 'Code page (chcp)' '65001' $cp ($cp -eq '65001')

# --- 3. コンソール出力エンコーディング ---
$conEnc = [Console]::OutputEncoding.WebName
Add-Row 'Console.OutputEncoding' 'utf-8' $conEnc ($conEnc -eq 'utf-8')

# --- 4. PYTHONUTF8 ---
$pyu = $env:PYTHONUTF8
if ([string]::IsNullOrEmpty($pyu)) { $pyu = '(未設定)' }
Add-Row 'PYTHONUTF8 env' '1' $pyu ($pyu -eq '1')

# --- 5. git core.quotepath (グローバル) ---
$qp = (git config --global core.quotepath)
if ([string]::IsNullOrEmpty($qp)) { $qp = '(未設定=既定true)' }
Add-Row 'git core.quotepath' 'false' $qp ($qp -eq 'false')

# --- 6. ExecutionPolicy (CurrentUser) ---
$ep = (Get-ExecutionPolicy -Scope CurrentUser).ToString()
Add-Row 'ExecutionPolicy (CurrentUser)' 'RemoteSigned 等' $ep ($ep -ne 'Restricted' -and $ep -ne 'Undefined')

# --- 7. PowerShell プロファイルの UTF-8 設定 ---
$profExists = Test-Path $PROFILE
$profHasEnc = $false
if ($profExists) {
    $pc = Get-Content $PROFILE -Raw -Encoding UTF8
    $profHasEnc = ($pc -match 'OutputEncoding')
}
$profState = if ($profExists) { if ($profHasEnc) { 'あり+UTF-8設定あり' } else { 'あり(UTF-8設定なし)' } } else { '(プロファイル無し)' }
Add-Row 'PowerShell profile UTF-8' 'UTF-8設定あり' $profState $profHasEnc

# --- 8. Python の実効出力エンコーディング(任意) ---
$pyEnc = (python -c "import sys;print(sys.stdout.encoding)" 2>$null)
if ([string]::IsNullOrEmpty($pyEnc)) { $pyEnc = '(python無し=対象外)' }
$pyOk = ($pyEnc -match 'utf-8') -or ($pyEnc -like '*対象外*')
Add-Row 'Python stdout encoding' 'utf-8' $pyEnc $pyOk

# --- 結果表示 ---
$rows | Format-Table -AutoSize | Out-String | Write-Host

$ng = @($rows | Where-Object { $_.Verdict -ne 'OK' })
Write-Host ""
if ($ng.Count -eq 0) {
    Write-Host "✅ すべてOKです。追加の対策は不要です。" -ForegroundColor Green
} else {
    Write-Host ("⚠️ 「要検討」が " + $ng.Count + " 件あります。README の対策カタログと templates/ を見て、必要な分だけ手動で適用してください。") -ForegroundColor Yellow
    Write-Host "   (このスクリプトは自動で変更しません)" -ForegroundColor DarkGray
}
Write-Host ""
