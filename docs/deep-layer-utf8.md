# 深層レイヤーの文字化け対策 — サブエージェント / バックグラウンド / ローカルLLM

端末やgitの設定(表層)を直しても、**自分のコードが外部プロセスを呼ぶ時**に別の文字化けが起きることがあります。この文書はその「深層」を扱います。

---

## 結論(先に)

| レイヤー | 日本語は化ける? | 理由 |
|---|---|---|
| サブエージェントへの引き継ぎ | ❌ 化けない | ツール内部の受け渡しはUTF-8。端末のCP932とは別レイヤー |
| バックグラウンドタスクの出力 | △ 端末設定次第 | 端末がUTF-8なら安全。ログの読み書きは同じUTF-8で揃える |
| Python から外部コマンド/LLM呼び出し | ⚠️ **ここが本命** | `encoding` 未指定だと既定(CP932)でデコードして化ける |
| Ollama など HTTP API | ❌ ほぼ化けない | `requests` がUTF-8で処理。`format=json` でJSON強制するとさらに堅牢 |

**表層(端末・git)より、自分のコードの `subprocess` と `open()` の方が事故りやすい**、が要点です。

---

## 1. Python から外部プロセスを呼ぶ時(最重要)

`subprocess` は `encoding` を指定しないと、Windowsでは既定の CP932 でデコードし、日本語が化けたり例外で落ちたりします。

```python
import subprocess

result = subprocess.run(
    ["some-cli", "-p"],
    input=prompt,          # プロンプトは引数でなく標準入力で渡す
    capture_output=True,
    text=True,
    encoding="utf-8",      # ← 必須。既定に任せない
    errors="replace",      # ← 不正バイトが来ても落とさず継続
    timeout=180,
)
```

- **`encoding="utf-8"` を必ず明示。** 「システムの自動推測」に任せないこと。
- **`errors="replace"`** を付けると、万一壊れたバイトが来ても例外で全滅せず、その1文字だけ `` に置換して処理を続けられます。
- **プロンプトはコマンドライン引数ではなく `input=`(標準入力)で渡す。** `%` `&` `|` などLP本文中の特殊文字がWindowsのコマンド解釈に引っかかるのを避けられます。

---

## 2. ファイルI/O と JSON

```python
# 読み書きは必ず encoding を明示
text = path.read_text(encoding="utf-8")
path.write_text(data, encoding="utf-8")

# JSON は日本語をエスケープさせない
import json
json.dumps(obj, ensure_ascii=False, indent=2)   # "入札" ではなく "入札"
```

- `ensure_ascii=False` を付けないと、日本語が `入...` の巨大なエスケープ列になり、トークンも無駄に消費します。
- **Excelで開くCSVだけ** は BOM 付き(`encoding="utf-8-sig"`)。逆にコード・JSON・設定ファイルには **BOMを付けない**(LinuxツールやコンパイラがBOMをゴミと誤認します)。

---

## 3. ローカルLLM(Ollama など)

CLI(`ollama run`)を直に叩くより、**HTTP API を `requests` で呼ぶ方が堅牢**です。

```python
import requests
resp = requests.post(
    "http://localhost:11434/api/generate",
    json={"model": "your-model", "prompt": prompt,
          "stream": False, "format": "json",
          "options": {"temperature": 0, "seed": 42}},
    timeout=300,
)
resp.raise_for_status()
answer = resp.json()["response"]   # requests が UTF-8 で処理してくれる
```

- `requests` の `.json()` はレスポンスをUTF-8として扱うため、端末のコードページに左右されません。
- `format="json"` を付けるとモデルがJSONで返すよう強制され、壊れた出力の救済処理が減ります。
- どうしてもCLIを使うなら、`subprocess` の項(第1章)と同じく `encoding="utf-8"` + 標準入力渡しにします。

---

## 4. 「AIが作業を見失う」対策(文字化けとは別問題)

サブエージェントやバックグラウンドに仕事を渡した時、内容が化けなくても **文脈が足りずにAIが迷子になる** ことがあります。これは文字コードではなく **引き継ぎ設計** の問題です。

- **引き継ぎプロンプトは自己完結にする。** 「このファイルの続き」ではなく、対象パス・前提・ゴール・成功条件を毎回明記する。相手はこの会話の記憶を持っていません。
- **構造化する。** 箇条書きや `<task></task>` のようなタグで、やること・制約・出力形式を分ける。
- **1エージェント=1責務。** 「調べて、直して、テストして、公開して」を1つに詰め込まない。分割すると各自が迷わない。
- **成功条件を数値・事実で書く。** 「良い感じに」ではなく「テストが全緑」「該当行が0件」など、達成を自分で判定できる形にする。

---

## チェックリスト

```
□ subprocess に encoding="utf-8", errors="replace" を付けたか
□ プロンプトは標準入力(input=)で渡しているか
□ open() / read_text / write_text に encoding="utf-8" を付けたか
□ json.dumps に ensure_ascii=False を付けたか
□ Excel用CSVだけ utf-8-sig、コード/JSONにはBOMを付けていないか
□ ローカルLLMは HTTP API(requests)経由か
□ サブエージェントへの指示は自己完結・構造化・単一責務か
```
