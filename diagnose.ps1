# =====================================================================
# diagnose.ps1 v2 - Claude Code Windows UTF-8 & Anti-Hallucination Kit
# 環境診断(読み取り専用・このスクリプトは何も変更しません)
# Read-only diagnostics. This script changes NOTHING on your system.
# =====================================================================
$ErrorActionPreference = 'SilentlyContinue'

Write-Host ""
Write-Host "==== Claude Code Windows UTF-8 & Anti-Hallucination Kit / 環境診断 v2 ====" -ForegroundColor Cyan
Write-Host "(read-only: 何も変更しません / changes nothing)" -ForegroundColor DarkGray
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

# ==========================================
# A. 表層UTF-8(古典的な文字化け対策)
# ==========================================

# --- 1. OS / PowerShell バージョン ---
$psv = $PSVersionTable.PSVersion.ToString()
Add-Row 'PowerShell version' '5.1 or 7.x' $psv $true

# --- 2. Windows Terminal or conhost ---
$isWT = ($env:WT_SESSION -ne $null -and $env:WT_SESSION -ne '')
$termName = if ($isWT) { 'Windows Terminal' } else { 'conhost / その他 (legacy console)' }
Add-Row 'Terminal host' 'Windows Terminal (推奨)' $termName $isWT

# --- 3. コードページ ---
$cpRaw = (chcp)
$cp = ($cpRaw -replace '[^0-9]', '')
Add-Row 'Code page (chcp)' '65001' $cp ($cp -eq '65001')

# --- 4. コンソール出力エンコーディング ---
$conEnc = [Console]::OutputEncoding.WebName
Add-Row 'Console.OutputEncoding' 'utf-8' $conEnc ($conEnc -eq 'utf-8')

# --- 5. PYTHONUTF8 ---
$pyu = $env:PYTHONUTF8
if ([string]::IsNullOrEmpty($pyu)) { $pyu = '(未設定)' }
Add-Row 'PYTHONUTF8 env' '1' $pyu ($pyu -eq '1')

# --- 6. TEMP パスに日本語が含まれていないか ---
$tempPath = $env:TEMP
$tempAscii = ($tempPath -match '^[\x20-\x7E]+$')
Add-Row 'TEMP path (ASCII only)' 'ASCII のみ' $tempPath $tempAscii

# --- 7. git core.quotepath (グローバル) ---
$qp = (git config --global core.quotepath); if ([string]::IsNullOrEmpty($qp)) { $qp = '(未設定=既定true)' }
Add-Row 'git core.quotepath' 'false' $qp ($qp -eq 'false')

# --- 8. ExecutionPolicy (CurrentUser) ---
$ep = (Get-ExecutionPolicy -Scope CurrentUser).ToString()
Add-Row 'ExecutionPolicy (CurrentUser)' 'RemoteSigned 等' $ep ($ep -ne 'Restricted' -and $ep -ne 'Undefined')

# --- 9. PowerShell プロファイルの UTF-8 設定 ---
$profExists = Test-Path $PROFILE
$profHasEnc = $false
if ($profExists) {
    $pc = Get-Content $PROFILE -Raw -Encoding UTF8
    $profHasEnc = ($pc -match 'OutputEncoding')
}
$profState = if ($profExists) { if ($profHasEnc) { 'あり+UTF-8設定あり' } else { 'あり(UTF-8設定なし)' } } else { '(プロファイル無し)' }
Add-Row 'PowerShell profile UTF-8' 'UTF-8設定あり' $profState $profHasEnc

# --- 10. Python の実効出力エンコーディング(任意) ---
$pyEnc = (python -c "import sys;print(sys.stdout.encoding)" 2>$null)
if ([string]::IsNullOrEmpty($pyEnc)) { $pyEnc = '(python無し=対象外)' }
$pyOk = ($pyEnc -match 'utf-8') -or ($pyEnc -like '*対象外*')
Add-Row 'Python stdout encoding' 'utf-8' $pyEnc $pyOk

# ==========================================
# B. AI連携チェック(嘘の完了報告 対策)
# ==========================================

# --- 11. Claude Code CLI の有無 ---
$claudeCmd = Get-Command claude -ErrorAction SilentlyContinue
$claudeState = if ($claudeCmd) { $claudeCmd.Source } else { '(未検出=対象外)' }
Add-Row 'Claude Code CLI (claude)' 'PATH に存在' $claudeState ($claudeCmd -ne $null -or $claudeState -like '*対象外*')

# --- 12. Ollama の有無(ローカルLLM) ---
$ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
$ollamaState = if ($ollamaCmd) { $ollamaCmd.Source } else { '(未検出=対象外)' }
Add-Row 'Ollama CLI' 'PATH に存在 or 未使用' $ollamaState $true  # 未検出でもOK扱い(必須ではない)

# --- 13. git リモート疎通(push偽装検知の前提) ---
$inRepo = (git rev-parse --is-inside-work-tree 2>$null)
if ($inRepo -eq 'true') {
    $remoteHead = (git ls-remote origin HEAD 2>$null) -split '\s+' | Select-Object -First 1
    $localHead = (git rev-parse HEAD 2>$null)
    if ([string]::IsNullOrEmpty($remoteHead)) {
        $syncState = '(リモート応答なし)'
        $syncOk = $false
    } elseif ($remoteHead -eq $localHead) {
        $syncState = '同期 (SHA一致)'
        $syncOk = $true
    } else {
        $syncState = "未同期 local=$($localHead.Substring(0,7)) remote=$($remoteHead.Substring(0,7))"
        $syncOk = $false
    }
} else {
    $syncState = '(gitリポジトリ外=対象外)'
    $syncOk = $true
}
Add-Row 'git local vs remote HEAD' 'SHA一致 or 対象外' $syncState $syncOk

# --- 14. CLAUDE.md に言語ルール記載があるか(カレントディレクトリ) ---
$claudeMd = Join-Path (Get-Location) 'CLAUDE.md'
if (Test-Path $claudeMd) {
    $md = Get-Content $claudeMd -Raw -Encoding UTF8
    $hasLangRule = ($md -match '日本語で(回答|返答|answer|respond)' -or $md -match 'Always respond in Japanese')
    $mdState = if ($hasLangRule) { '言語ルールあり' } else { 'あるが言語ルール未記載' }
    Add-Row 'CLAUDE.md language rule' '言語ルールあり or 対象外' $mdState $hasLangRule
} else {
    Add-Row 'CLAUDE.md language rule' '言語ルールあり or 対象外' '(CLAUDE.md無し=対象外)' $true
}

# ==========================================
# 結果表示
# ==========================================

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
Write-Host "==== 補足: AIの嘘の完了報告を防ぐ運用ルール ====" -ForegroundColor Cyan
Write-Host "docs/anti-hallucination-mojibake.md を読み、実測裏取り3点セット" -ForegroundColor DarkGray
Write-Host "(Grep -c / git ls-remote / git show HEAD:) をCLAUDE.mdに組み込んでください。" -ForegroundColor DarkGray
Write-Host ""
