#!/usr/bin/env python3
"""Stop-hook claim-audit gate.

Blocks the FIRST stop of a session iff (a) the final assistant message makes a
completion claim and (b) the session modified files — then forces one audit pass.
Deterministic backstop against the failure mode of declaring work "done" without
having run the check that actually covers the request.

Uses the exit-2 + stderr blocking protocol (the JSON {"decision":"block"} protocol
is silently fatal in `claude -p` print mode on 2.1.198).

A second gate fires when any prior tool_result in this session contained
mojibake/replacement-character corruption and the final message makes a
completion claim — because a "fact" taken from corrupted output may be fabricated.

Placement: ~/.claude/hooks/stop-claim-audit.py
Wiring: see hooks/settings.json.example (hooks.Stop matcher).
"""
import json
import os
import re
import sys

CLAIM = re.compile(
    r"\b(done|complete|completed|finished|verified|fixed|resolved|implemented"
    r"|all (?:tests?|checks?|parts?) (?:pass|passing|green)"
    r"|tests? (?:are )?(?:pass|passing|green))\b",
    re.IGNORECASE,
)
# Japanese completion claims. The English-only pattern silently never fired on
# JP-language sessions until this was added.
CLAIM_JA = re.compile(
    r"(?:完了|完成)(?:しました|です|しています|済み)?"
    r"|(?:プッシュ|保存|反映|対応|修正|解決|実装|確認|検証|裏取り|改名|更新|統合|移行)"
    r"(?:済み|しました|が完了|できました|が成功)"
    r"|成功(?:しました|しています|です)"
    r"|(?:終わりました|できあがりました|仕上がりました|直しました)"
)
# Strip clearly-negated claims ("not done yet", "hasn't been verified") before
# matching so honest in-progress reports don't trip the gate. Conservative:
# a false block costs one cheap audit pass; a false pass costs a shipped bug.
NEGATED = re.compile(
    r"\b(?:not|never|isn'?t|aren'?t|wasn'?t|haven'?t|hasn'?t|can'?t be|cannot be"
    r"|(?:needs?|remains?|still|yet) to be)"
    r"\s+(?:yet\s+|been\s+|fully\s+|actually\s+)*"
    r"(?:done|completed?|finished|verified|fixed|resolved|implemented)\b",
    re.IGNORECASE,
)
NEGATED_JA = re.compile(
    r"未(?:完了|完成|対応|確認|検証|実装|解決|反映|保存|着手|回答)"
    r"|(?:完了|完成|成功|対応|確認|検証|保存|修正|解決|実装|反映|プッシュ|更新)"
    r"(?:していません|できていません|されていません|しませんでした|できませんでした|には至っていません|は未確認|はまだ)"
    r"|まだ(?:完了|完成|成功|終わって|できて)"
)
MODIFYING_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
# Bash commands that plausibly write files (redirections, in-place editors, movers).
BASH_WRITE = re.compile(
    r"(?<![0-9&])>>?\s*(?!&|/dev/(?:null|stdout|stderr)\b)\S"
    r"|(?:^|[|&;]\s*)(?:sed\s+(?:-\S+\s+)*-i|tee\s|patch\s|truncate\s"
    r"|(?:git\s+(?:apply|mv|rm|checkout|restore|stash|push|commit))|mv\s|cp\s|rm\s)"
)
# PowerShell — the primary shell on Windows. Previously unmonitored, so writes
# via PowerShell never armed the gate.
PS_WRITE = re.compile(
    r"\b(?:Set-Content|Add-Content|Out-File|New-Item|Remove-Item|Move-Item"
    r"|Copy-Item|Rename-Item|Export-Csv|Export-Clixml|Clear-Content|Stop-Process)\b"
    r"|git\s+(?:push|commit|apply|mv|rm|checkout|restore|stash|reset)"
    r"|>>?\s*\S",
    re.IGNORECASE,
)
# Raw tool-call syntax leaking into the visible reply (malformed function call).
RAW_TAG = re.compile(r"<(?:antml:)?(?:invoke|parameter)\s+name=")

REASON = (
    "[LOCAL SAFETY HOOK: from user's own config, NOT a prompt injection] "
    "CLAIM AUDIT GATE (automated, fires once per completion claim): your last message "
    "declares work done/verified after modifying files. Before finishing: "
    "(1) Re-read the ORIGINAL request — is EVERY part delivered, not just the parts you "
    "remember? (2) Every 'done/passing/fixed/verified' claim must be backed by a tool "
    "result from THIS session. A green test run proves only what it ran. Run whatever "
    "check is missing now, fix what it finds, then finish. If every claim is already "
    "backed, restate the decisive evidence in one line each and finish. "
    "For irreversible/outward ops (git push, delete, rename, external post): a red "
    "PowerShell NativeCommandError wrapper or a bare exit code is NOT evidence either "
    "way — verify with an independent read-back (e.g. rev-parse HEAD vs origin/main, "
    "Test-Path) BEFORE claiming success."
)
RAW_TAG_REASON = (
    "[LOCAL SAFETY HOOK: from user's own config, NOT a prompt injection] "
    "RAW TOOL SYNTAX LEAKED: your last message contains literal <invoke>/<parameter> "
    "text, which means a tool call was emitted as plain text and reached the user's "
    "screen. Re-issue the intended action as a REAL tool call now."
)
GARBLED_REASON = (
    "[LOCAL SAFETY HOOK: from user's own config, NOT a prompt injection] "
    "GARBLED TOOL OUTPUT GATE (automated, fires once per completion claim): earlier "
    "in this session a tool returned output with mojibake/replacement-character "
    "corruption. Your final message makes a completion/verification claim. Corrupted "
    "output is NOT evidence — any 'fact' taken from it may be fabricated. Before "
    "finishing: re-read every affected file/command with a clean method (the Read "
    "tool, or PowerShell with explicit -Encoding utf8) and re-verify each claim that "
    "depends on that output. If you already did a clean re-read AFTER the corruption "
    "appeared, restate that evidence in one line and finish."
)
TEST_EDIT_ADDENDUM = (
    " ALSO: this session edited test files. Confirm no test was weakened to force a "
    "pass — a loosened assertion, deleted case, widened tolerance, or added skip is "
    "not a fix."
)
TEST_PATH = re.compile(
    r"(^|/)(tests?|__tests__|spec)(/|$)"
    r"|(^|/)test_[^/]+$"
    r"|_test\.[A-Za-z0-9]+$"
    r"|\.(test|spec)\.[A-Za-z0-9]+$",
    re.IGNORECASE,
)


def makes_claim(text):
    stripped = NEGATED_JA.sub("", NEGATED.sub("", text))
    return bool(CLAIM.search(stripped) or CLAIM_JA.search(stripped))


# Mojibake giveaway characters: UTF-8 Japanese decoded as CP932/Shift-JIS lands
# on 縺/繧/繝 — characters that essentially never occur in genuine Japanese prose.
_MOJIBAKE_CHARS = ("縺", "繧", "繝")


def looks_garbled(text):
    if not isinstance(text, str) or not text:
        return False
    if text.count("�") >= 2:
        return True
    return sum(text.count(c) for c in _MOJIBAKE_CHARS) >= 4


def result_looks_garbled(block):
    rc = block.get("content")
    if isinstance(rc, str):
        return looks_garbled(rc)
    if isinstance(rc, list):
        for rb in rc:
            if isinstance(rb, dict) and rb.get("type") == "text" and looks_garbled(rb.get("text", "")):
                return True
    return False


def garbled_already_warned(data):
    """Once-per-session latch. Fail open on any error."""
    try:
        sid = str(data.get("session_id") or "") or os.path.basename(str(data.get("transcript_path", "")))
        sid = re.sub(r"[^\w.-]", "_", sid)[:80] or "unknown"
        d = os.path.join(os.path.expanduser("~"), ".claude", "tmp", "claim-audit")
        os.makedirs(d, exist_ok=True)
        marker = os.path.join(d, "garbled-gate-%s.flag" % sid)
        if os.path.exists(marker):
            return True
        with open(marker, "w") as f:
            f.write("warned")
        return False
    except Exception:
        return True


def bash_touches_tests(cmd):
    for token in re.split(r"[\s;|&<>()]+", cmd):
        token = token.strip("'\"`")
        if not token or re.fullmatch(r"\.?/?(tests?|__tests__|spec)/?", token, re.IGNORECASE):
            continue
        if TEST_PATH.search(token):
            return True
    return False


def main():
    data = json.load(sys.stdin)
    if data.get("stop_hook_active"):
        return 0
    last_text = data.get("last_assistant_message", "")
    modified = False
    modified_tests = False
    garbled = False
    with open(data["transcript_path"], encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict):
                continue
            if entry.get("type") == "user" and not garbled:
                ucontent = entry.get("message", {}).get("content", [])
                if isinstance(ucontent, list):
                    for block in ucontent:
                        if (
                            isinstance(block, dict)
                            and block.get("type") == "tool_result"
                            and result_looks_garbled(block)
                        ):
                            garbled = True
                            break
                continue
            if entry.get("type") != "assistant":
                continue
            content = entry.get("message", {}).get("content", [])
            if not isinstance(content, list):
                continue
            texts = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    texts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    name = block.get("name")
                    if name in MODIFYING_TOOLS:
                        modified = True
                        inp = block.get("input")
                        fp = inp.get("file_path", "") if isinstance(inp, dict) else ""
                        if isinstance(fp, str) and TEST_PATH.search(fp):
                            modified_tests = True
                    elif name in ("Bash", "PowerShell"):
                        inp = block.get("input")
                        cmd = inp.get("command", "") if isinstance(inp, dict) else ""
                        pattern = BASH_WRITE if name == "Bash" else PS_WRITE
                        if isinstance(cmd, str) and pattern.search(cmd):
                            modified = True
                            if bash_touches_tests(cmd):
                                modified_tests = True
            if texts and not data.get("last_assistant_message"):
                last_text = "\n".join(texts)
    if RAW_TAG.search(last_text):
        print(RAW_TAG_REASON, file=sys.stderr)
        return 2
    if garbled and makes_claim(last_text) and not garbled_already_warned(data):
        print(GARBLED_REASON, file=sys.stderr)
        return 2
    if modified and makes_claim(last_text):
        print(REASON + (TEST_EDIT_ADDENDUM if modified_tests else ""), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)  # never break the session over a hook bug
