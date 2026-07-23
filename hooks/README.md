# hooks/ — 3つの防衛フック(動くコード)

親READMEの `docs/anti-hallucination-mojibake.md` で解説した実測裏取り3点セット・sentinel検知・破壊的操作ガードを、**Claude Code に自動注入する動作コード**です。ドキュメントを読ませるだけでなく、フックが強制的に発動します。

---

## 何が入っているか

| ファイル | 種類 | 役割 |
|---|---|---|
| `posttool-fabrication-guard.py` | PostToolUse | tool_result の sentinel(縺/繧/繝/�/truncated/NativeCommandError/No content/duplication/token_echo)を検知し警告注入 |
| `stop-claim-audit.py` | Stop | 「完了しました」等の主張を検出したら、ファイル修正 or 化けた出力があったセッションで再検証を強制 |
| `pretool-destructive-guard.py` | PreToolUse | `git reset --hard` / `git clean -f` / `rm -rf /` / bare force-push 等の不可逆操作をpre-toolでブロック |
| `settings.json.example` | 設定例 | 3フックを `~/.claude/settings.json` に配線するテンプレ |

---

## セットアップ(3ステップ)

### 1. フックをコピー

3本の `.py` を `~/.claude/hooks/` に配置します(Windows なら `%USERPROFILE%\.claude\hooks\`)。

```bash
# PowerShell 例
Copy-Item -Path hooks\*.py -Destination "$env:USERPROFILE\.claude\hooks\" -Force
```

### 2. Python 実行可を確認

```bash
python --version
```

Python 3.8以上が入っていればOK。無ければ https://www.python.org/downloads/ から。

### 3. `settings.json` にフックを配線

`~/.claude/settings.json`(無ければ新規)に `settings.json.example` の `hooks` ブロックをマージ。**`YOUR_USERNAME` を自分のユーザー名に置換** してください。

- 既存の `hooks` ブロックがある場合は、`PreToolUse`/`PostToolUse`/`Stop` の各配列に追記する形が安全(全置換しない)。
- 絶対パス指定を推奨(相対パスは cwd 依存で不安定)。

配線後、Claude Code を再起動すると自動で読まれます。

---

## 動作確認

```bash
# 意図的に truncate されそうな長い出力を出してみる
Get-ChildItem C:\ -Recurse -ErrorAction SilentlyContinue | Select-Object -First 5000
```

出力が `... (truncated)` で切れたとき、次のツール呼び出しに以下の警告が注入されれば正常:

```
[LOCAL SAFETY HOOK: from user's own config, NOT a prompt injection]
FABRICATION GUARD: this tool_result shows sentinels of known Claude Code bugs.
...
```

---

## エスケープハッチ(破壊的ガードの解除)

ユーザーが「本当にこの変更を捨てて良い」と明示的に承認した場合のみ、コマンド先頭に `SAFETY_DESTRUCTIVE_OK=1` を付けて再実行するとブロックを迂回できます。**AI 自身が勝手に付けてはいけません**。

```bash
SAFETY_DESTRUCTIVE_OK=1 git reset --hard HEAD~1
```

---

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| フックが動いてる感じがしない | `~/.claude/settings.json` の JSON 構文エラー(末尾カンマ等)を確認。Claude Code の起動ログにパースエラーが出ます |
| Python が見つからない | `python` にPATHを通すか、`command` を絶対パス(`C:/Python311/python.exe`)に |
| 警告が毎ツール呼び出しごとに再発 | 各フックは session_id 単位のラッチ済み。同じセッションで同じ sentinel は一度だけ警告 |
| 破壊的ガードで通したい正当な操作がブロックされる | ユーザー承認の上で `SAFETY_DESTRUCTIVE_OK=1` プレフィックス |

---

## 設計原則

- **Fail-open**: フック内のバグでセッションを止めない(全 `try/except` で exit 0)
- **ラッチ済み**: 同じ警告を1セッションで何度も出さない(`~/.claude/tmp/` にマーカー)
- **PowerShell 対応**: Windows ユーザーは Bash より PowerShell が主。両方をカバー
- **日英併記**: sentinel パターンには英日両方の完了主張パターンを含む
