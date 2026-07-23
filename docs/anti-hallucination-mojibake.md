# 化けたtool出力をAIに信じさせない — 実測裏取りで嘘の完了報告を止める

Claude Code / Cursor / Cline などのAIコーディング agent が「完了しました」「pushしました」と言ったのに **実際は何も変わっていない** — この事故は多くが、tool_result が化け・欠け・truncate されていたのを **AIが成功として解釈した** ことで起きます。

このドキュメントは、その **B系の事故(AIの嘘の完了報告)** を人間側とプロンプト側の両方でブロックするための実践集です。表層のUTF-8対策(README・`docs/deep-layer-utf8.md`)だけでは防げません。

---

## なぜ表層UTF-8だけでは足りないのか

| 層 | 何が起こる | UTF-8修正で直る? |
|---|---|---|
| 端末 | `縺ゅ＞縺` のように化けて画面に出る | ✅ 直る |
| gitファイル名 | `\350\251\225` として出る | ✅ 直る |
| **AIが化けた出力を成功と解釈** | 「Edit成功しました」と続けて次の作業へ | ❌ **直らない** |
| **AIが truncate 出力を全文と誤認** | 見えていない部分を推測で埋める | ❌ **直らない** |

**Bは受信側=AI の解釈問題**であり、送信側(端末・git)をUTF-8化しても消えません。AIに「疑うトリガー」を仕込む運用が別途必要です。

---

## 既知の関連バグ(2026年時点)

| Issue | 症状 | 影響 |
|---|---|---|
| Anthropic #64409 | Edit tool が実ファイルを変更せず success を返す | 「修正しました」が架空になる |
| Anthropic #61471 | Read tool が返却内容を欠損させる(空 or 部分) | AIが存在しない前提で判断 |
| Anthropic #17407 | Bash exit code の誤検知(exit 0 なのに失敗扱い等) | 成功をリトライして二重実行 |
| Anthropic #64317 | 並列 tool_call 4件以上で buffer bleed(出力混線) | 別コマンドの結果を混ぜて解釈 |
| Anthropic #36596 | 長い出力の末尾が `... (truncated)` で切れる | 見えない部分を推測で補う |
| Anthropic #42417 | UTF-8ファイルをCP932でRead → 縺/繧/繝 化け | 化けた文字列を実体と誤認 |
| Anthropic #18856 | Windowsで Bash tool が `(No content)` 空返し | 存在しない状態を確定扱い |
| posh-git #109 | PowerShell 5.1 で git stderr が ErrorRecord に包まれ `$?=false` | exit 0 の成功が「失敗」扱い |

これらは表層のUTF-8とは無関係に発生します。**修正を待つのではなく、運用で検知する**方針が現実解です。

---

## 実測裏取り3点セット(必ずこれで検知)

AIが「完了しました」「pushしました」「保存しました」と言った **直前** に、以下のうち該当する1つを独立ツールで実行し、実測値で判定します。モデルの記憶を信用しないのがポイントです。

### 1. ファイル編集の裏取り

```bash
# 変更後にあるはずの文字列が本当に入っているか
grep -c "変更後の文字列" 対象パス
```

- 件数 ≥ 1 なら本物、0 なら Edit がサイレント失敗している(#64409)。
- Claude Code なら `Grep` ツールで `output_mode=count`。

### 2. git push の裏取り

```bash
git ls-remote origin HEAD    # リモートの最新SHA
git rev-parse HEAD           # ローカルの最新SHA
```

- 2つのSHAが完全一致 → 本当にpush済み。
- 不一致 → push は失敗、または実行されていない。「pushしました」は嘘。

### 3. Read結果への疑い

```bash
git show HEAD:対象パス | head -20
```

- Read tool が返した内容と、gitに記録された実体の1行目・末行を対比。
- ズレていれば Read が欠損している(#61471)。

これら3つを CLAUDE.md に「完了主張の直前に必ず実行」ルールとして書いておくと、AIが自主的に自分の嘘を検出するようになります。

---

## 疑うべき出力パターン(sentinel検知)

以下のパターンを tool_result 内に見つけたら、その結果は **信用せず即再取得** します。人間が目視でも、AIプロンプトの `<detection_rules>` に入れても効きます。

| Sentinel | 意味 | 対応 |
|---|---|---|
| `... (truncated)` | 出力が切り詰められた(#36596) | offset/limit 指定で分割再取得 |
| `NativeCommandError` | PS 5.1 の git stderr 誤解釈(posh-git #109) | 末尾に `; $LASTEXITCODE` を付けて再実行し、実際の終了コードで判定 |
| `(No content)` | ツールが空返しした | 別ツール(Bash `type` 等)で実体確認 |
| `Cancelled: parallel tool call` | 並列上限で切られた(#64317) | 順次実行に切替 |
| `縺` `繧` `繝` が2文字以上連続 | CP932 誤解釈による化け | encoding指定して再取得 |
| `U+FFFD`(�)が2文字以上 | バイト列の途中で切れた | offset を戻して再取得 |
| 同じ行が2倍以上echo | buffer bleed(#64317) | 単発呼び出しで再実行 |
| `Access is denied` の直後に成功メッセージ | 権限不足を無視 | 権限確認から再開 |

---

## 並列 tool_call は3件までに制限する

Anthropic Issue #64317(buffer bleed workaround)より、**同時実行のtool_callは3件まで**にすると混線事故が激減します。

- Claude Code の CLAUDE.md に「並列 tool_call は3件までに制限」を明記。
- 4件以上必要な場面では、意図的にバッチ分割する。
- 特に **Read + Grep + Bash の混合4件同時実行** が事故率高。

---

## セッション劣化の予防

長時間セッションでは tool_result のノイズが累積し、AIが化けを検出する感度が落ちます。

- 2時間経過、または tool_call 60本超で意図的に `/compact` するか新規チャットに移行。
- Windowsパス操作は原則 PowerShell(Bash tool は非ASCIIパスで壊れやすい・#64317系)。
- 定期的に `diagnose.ps1` を走らせ、環境側の劣化(chcpが932に戻る等)を早期検知。

---

## CLAUDE.md に貼るテンプレ

以下をプロジェクトの CLAUDE.md か `~/.claude/CLAUDE.md` に追記すると、AIが自主的に嘘を検出する運用になります。

```markdown
## 完了主張の直前ルール(実測裏取り3点セット)

「完了」「成功」「push済」「保存済」を言う前に、以下のうち該当するものを1回だけ実行する。
モデルの記憶ではなく独立ツールでの実測を根拠にする(Anthropic Issue #64409 / #61471 / #17407 対策)。

- ファイル編集 → `Grep -c <変更後文字列> <path>` で件数≥1 を確認
- git push   → `git ls-remote origin HEAD` と `git rev-parse HEAD` のSHA一致
- Read疑い   → `git show HEAD:<path> | head -20` と対比

## 疑うべき出力パターン(見たら即再取得)

以下のsentinelを検知したら、その tool_result は信用せず再取得する:
`... (truncated)` / `NativeCommandError` / `(No content)` /
`縺` `繧` `繝` が2文字以上 / U+FFFD が2文字以上 / 同じ行が2倍以上echo。

## 並列 tool_call の上限

同時実行の tool_call は最大3件(#64317 buffer bleed workaround)。
```

---

## チェックリスト

```
□ 実測裏取り3点セット(Grep -c / git ls-remote / git show HEAD:)をCLAUDE.mdに記載した
□ 疑うべき出力パターン(sentinel)一覧をCLAUDE.mdに記載した
□ 並列 tool_call を3件までに制限すると明記した
□ 2時間 or tool_call 60本で /compact する運用を決めた
□ Windowsパス操作はPowerShellを既定にすると明記した
□ 定期的に diagnose.ps1 を走らせる仕組みがある(週次など)
```
