# =====================================================================
# PowerShell プロファイル追記スニペット — 出力UTF-8化
# 追記先: $PROFILE
#   (通常: Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1)
#
# ⚠️ 既存のプロファイルがある人は、上書き前に必ずバックアップしてください。
#    このファイルの中身を「追記」する形が安全です(全置換しない)。
# =====================================================================

# 外部プログラム(git等)へ日本語をパイプで渡す時の化けを防ぐ
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

# コンソール出力をUTF-8に固定
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

# 注: [Console]::InputEncoding は日本語IMEと干渉する報告があるため、
#     意図的に変更していません。必要な人だけ自己責任で追加してください。
