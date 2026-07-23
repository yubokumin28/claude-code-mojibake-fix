# Claude Code Windows UTF-8 & Anti-Hallucination Kit

> Windows + PowerShell + Claude Code 環境で「日本語が文字化けする」「ツール出力が壊れる」「AIが化けた出力を鵜呑みにして **嘘の完了報告** を出す」を減らすための **診断ファースト** セットアップキット。
> A diagnose-first kit that reduces Japanese mojibake AND the false "task completed" reports Claude/AI agents produce when they trust broken tool output.

---

## ⚠️ 最初に必ず読んでください(重要)

このキットは **あなたのPCの状態を自動で書き換えません**。まず診断スクリプトで「今どうなっているか」を調べ、**結果を見て、自分に必要な対策だけを手動で適用**する設計です。

- **環境によって最適な設定は違います。** Windowsのバージョン、PowerShellのバージョン、既存の設定、使っている業務ソフトによって、必要な対策も、やってはいけない対策も変わります。
- **必ず `diagnose.ps1` を先に実行**し、自分の環境を把握してから導入してください。いきなりテンプレートを貼り付けないでください。
- **設定変更は自己責任で。** 既存の設定ファイル(PowerShellプロファイル等)がある人は、上書き前に必ずバックアップを取ってください。
- **🚫 Windowsシステムロケールの「ベータ: Unicode UTF-8を使用」は、このキットでは推奨しません。** 全アプリに波及し、古い業務ソフト・Excelマクロ・プリンタドライバなどで **新たな文字化けや不具合** を誘発する既知の地雷です。安易に有効化しないでください。

---

## これは何のためのもの?

Claude Code を Windows の日本語環境で使うと、こんな症状が出ることがあります。

### A. 表層の文字化け(古典的)

| 症状 | よくある原因 |
|---|---|
| コマンド出力の日本語が `縺ゅ＞縺` のように化ける | 端末がShift-JIS(CP932)のまま |
| gitで日本語ファイル名が `\350\251\225` と表示される | `core.quotepath` が既定(true) |
| `.ps1` の日本語コメントが化ける/動かない | ファイルがBOMなしUTF-8で、PowerShell 5.1がCP932と誤読 |
| ExcelでCSVを開くと化ける | BOMなしUTF-8をExcelがShift-JIS誤認 |
| AIが途中から英語で答える | 言語指定が固定されていない |

### B. AIが化けた出力を **信じて嘘の完了報告** を出す(2026年になって顕在化)

| 症状 | 実害 |
|---|---|
| Edit直後に「修正しました」と言うが実ファイルは変わっていない | 進捗が架空になる |
| 「git pushしました」と言うがリモートSHAは古いまま | 公開したつもりのコードが未公開 |
| Read結果が空 or 化けていたのに、AIが「内容を確認しました」と続ける | 存在しない情報を基に設計判断が進む |
| tool_result末尾が `... (truncated)` や `NativeCommandError` なのに成功扱い | サイレント失敗 |

**Bは表層のUTF-8を直しても消えません。** AI側が「化けた/欠けたtool出力」を成功として解釈する構造問題(Anthropic Issue #64409 / #61471 / #17407)であり、**受信側=人間とAIの両方に「疑うトリガー」を仕込む** 必要があります。

このキットはAとBを **測って・見える化して・必要な分だけ直す** ための道具です。

---

## 対象環境

- OS: Windows 10 / 11
- シェル: Windows PowerShell 5.1(Windows標準)または PowerShell 7
- ツール: Claude Code / Git / Python(任意) / Ollama(任意)

※ Mac・Linux はそもそもUTF-8が既定のため、Aは不要です。ただし **B(AIの嘘の完了報告)はOSに依存しない**ので、`docs/anti-hallucination-mojibake.md` は全OS共通で有用です。

---

## 使い方(3ステップ)

### 1. 環境を診断する(何も変更しません)

PowerShellを開いて、このフォルダで次を実行します。

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File .\diagnose.ps1
```

各項目について「推奨値 / あなたの値 / 判定(OK・要検討)」が表で出ます。**まずここで自分の弱点だけを把握**してください。

### 2. 結果を見て、必要な対策だけ手動で入れる

診断で「要検討」が出た項目だけ、`templates/` の該当ファイルを参考に適用します。全部やる必要はありません。

### 3. もう一度診断して確認する

適用後にもう一度 `diagnose.ps1` を実行し、「要検討」が消えたかを確認します。

### 4. AIとの運用ルールを追加する(B対策・重要)

`docs/anti-hallucination-mojibake.md` を読み、**「化けたtool_resultをAIに鵜呑みさせない」実測裏取り3点セット**をCLAUDE.mdやプロジェクト規約に組み込んでください。診断スクリプトでは検知できない、運用側の防衛策です。

---

## 対策カタログ(必要な分だけ)

| 対策 | 何をする | なぜ | リスク |
|---|---|---|---|
| 端末をUTF-8化 | `chcp 65001` を既定に | Shift-JIS化けを止める | 古いCP932専用コマンドの出力が化ける場合あり(稀) |
| PowerShellプロファイル | 出力エンコーディングをUTF-8固定 | exeへ日本語を渡す時の化け防止 | 既存プロファイルは要バックアップ |
| git `core.quotepath=false` | 日本語ファイル名をそのまま表示 | 可読性・トークン節約 | ほぼ無し |
| `.ps1` はBOM付きUTF-8で保存 | 日本語コメントの化け防止 | PS5.1がBOMなしをCP932誤読するため | 一部Linuxツールと共有する.ps1では非推奨 |
| Excel用CSVは `utf-8-sig` | BOM付きで保存 | Excelの誤認化け防止 | **コード/JSONにBOMは付けない** |
| CLAUDE.md に言語ルール | 「常に日本語で回答」等を明記 | 応答の安定 | トークン微増(数百/セッション) |
| **実測裏取り3点セット** | Edit/push/Readの直後に独立ツールで再確認 | AIの嘘の完了報告を検出 | トークン微増(数百/操作) |
| **並列tool_callを3件まで** | 4件以上同時実行を避ける | buffer bleed(#64317)回避 | 実行速度の若干低下 |

詳しい適用例は `templates/` を、AIの嘘対策は `docs/anti-hallucination-mojibake.md` を見てください。

---

## ファイル構成

```
diagnose.ps1                      … 環境診断v2(読み取り専用・何も変更しない)
templates/
  powershell-profile.ps1          … PowerShellプロファイルの例
  gitconfig-snippet.txt           … git設定の例
  CLAUDE.md.example               … Claude Code用 言語ルールの例(日英)
docs/
  deep-layer-utf8.md              … サブエージェント/バックグラウンド/ローカルLLMの化け対策
  anti-hallucination-mojibake.md  … 化けたtool出力をAIに信じさせないための実測裏取り(新規)
```

> **端末やgitの設定だけでは足りません。** 自作コードで `subprocess` や Ollama を呼ぶ、AIエージェントに仕事を渡す ―― こうした「深層」と「AIとの受け渡し」で化けや **嘘の完了報告** を防ぐ実践は [`docs/deep-layer-utf8.md`](docs/deep-layer-utf8.md) と [`docs/anti-hallucination-mojibake.md`](docs/anti-hallucination-mojibake.md) にまとめました。

---

## よくある質問

**Q. 診断スクリプトはPCを勝手に変更しませんか?**
A. しません。表示するだけの読み取り専用です。変更はすべてあなたが手動で行います。

**Q. システムロケールのUTF-8ベータを有効にすれば全部解決では?**
A. 一見そう見えますが、**非推奨**です。全アプリに影響し、古い業務ソフトで別の不具合を生む地雷です。このキットは「アプリ単位・設定単位」で安全に対処する方針です。

**Q. 全部の対策を入れるべき?**
A. いいえ。診断で「要検討」が出たものだけで十分です。ただし `docs/anti-hallucination-mojibake.md` の運用ルールは、Claude Code / Cursor / Cline など **AIエージェントを使う人全員に推奨** します。

**Q. AIが「完了しました」と言ったのに実際は変わっていませんでした。バグですか?**
A. 既知の症状です。Anthropic公式Issue #64409(Edit tool silent failure)/ #61471(Read返却の欠損)/ #17407(Bash exit code誤検知)で追跡中。当キットの `docs/anti-hallucination-mojibake.md` にある**実測裏取り3点セット**を運用に組み込むと検知できます。

---

## ライセンス

MIT License. 自由に使ってください。ただし **各自の環境で診断してから導入する** という前提を守ってください。設定変更による不具合の責任は負いかねます。
