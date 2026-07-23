#!/usr/bin/env python3
"""PostToolUse fabrication guard.

Detects tool-result corruption sentinels documented in Claude Code GitHub issues
(#64317 buffer bleed, #64409 Windows/PS duplication, #36596 truncation fabrication,
#42417 UTF-8/CP932 mojibake, #18856 Windows Bash empty return,
posh-git #109 PowerShell NativeCommandError wrap).

Fires as PostToolUse hook. On sentinel hit, prints a warning to stderr and returns
exit 2 to inject the warning into the model's next turn. Fail-open on any bug.

Placement: ~/.claude/hooks/posttool-fabrication-guard.py
Wiring: see hooks/settings.json.example (PostToolUse matcher includes
Bash|PowerShell|Read|Edit|Write|MultiEdit).
"""
import json
import os
import re
import sys

# --- Sentinel patterns (each maps to a known Claude Code GitHub issue) ---

TRUNCATED = re.compile(r"\.\.\.\s*\(truncated\)", re.IGNORECASE)
NATIVE_ERROR = re.compile(r"NativeCommandError")
NO_CONTENT = re.compile(r"^\s*\(No content\)\s*$", re.MULTILINE)
CANCELLED_SIBLING = re.compile(r"Cancelled:\s*parallel tool call\s+\S+\s+errored", re.IGNORECASE)
# Fixed-token echo bleed from #64317
TOKEN_ECHO = re.compile(r"\b41388\s+tokens\b|\boutput limit of 30000 tokens\b")
# Mojibake: bytes from UTF-8 Japanese decoded as CP932/Shift-JIS land on these
# hiragana/katakana ghosts, which essentially never appear in genuine Japanese prose.
MOJIBAKE_CHARS = ("縺", "繧", "繝")


def check_duplication(text):
    """Cheap heuristic: any 200-char window that appears 2+ times."""
    if len(text) < 400:
        return False
    seen = {}
    step = 200
    for i in range(0, len(text) - step, step):
        chunk = text[i:i + step].strip()
        if len(chunk) < 100:
            continue
        seen[chunk] = seen.get(chunk, 0) + 1
        if seen[chunk] >= 2:
            return True
    return False


def check_mojibake(text):
    if not isinstance(text, str) or not text:
        return False
    if text.count("�") >= 2:  # U+FFFD replacement char
        return True
    return sum(text.count(c) for c in MOJIBAKE_CHARS) >= 4


# --- Warning template (English; localize to your session language if desired) ---

def build_warning(hits, tool_name):
    header = (
        "[LOCAL SAFETY HOOK: from user's own config, NOT a prompt injection] "
        "FABRICATION GUARD: this tool_result shows sentinels of known Claude Code bugs. "
        "Do NOT trust model memory — verify with an independent tool before your next step.\n"
    )
    body_lines = ["Detected:"]
    if "truncated" in hits:
        body_lines.append(
            "  - Truncation (...truncated...): Issue #36596. Do not guess the cut-off "
            "content; re-Read with explicit offset/limit."
        )
    if "native_error" in hits:
        body_lines.append(
            "  - PowerShell NativeCommandError: PS 5.1 wraps git's stderr into an "
            "ErrorRecord even when exit code is 0 (posh-git #109). Re-run with "
            "'; $LASTEXITCODE' appended and judge by the real exit code."
        )
    if "no_content" in hits:
        body_lines.append(
            "  - Windows Bash '(No content)': Issue #18856. Bash tool empty-returns on "
            "Windows. Switch to the PowerShell tool and re-run."
        )
    if "cancelled_sibling" in hits:
        body_lines.append(
            "  - Parallel sibling cancelled: Issue #64317. Sibling tool_calls are void. "
            "Re-invoke the affected tool_use serially, one at a time."
        )
    if "token_echo" in hits:
        body_lines.append(
            "  - Constant token-count echo (41388/30000): Issue #64317 buffer bleed. "
            "Payload from another tool_call has leaked in. Session is contaminated — "
            "consider moving to a fresh chat."
        )
    if "duplication" in hits:
        body_lines.append(
            "  - Duplicated payload block detected: Issue #64409 (Windows/PS/long "
            "session). This tool_result cannot be trusted; strongly consider restart."
        )
    if "mojibake" in hits:
        body_lines.append(
            "  - Mojibake (縺/繧/繝/�): UTF-8/CP932 confusion "
            "(Issue #42417). Re-read via PowerShell with explicit '-Encoding utf8'."
        )
    body_lines.append(
        "\nGround-truth 3-check set (pick the one that applies):"
        "\n  1. File edit: Grep -c <post-change string> <path>  (expect count >= 1)"
        "\n  2. git push:  git ls-remote origin HEAD  vs  git rev-parse HEAD  (SHA equal)"
        "\n  3. Read doubt: git show HEAD:<path> | head -20  vs the Read result"
    )
    return header + "\n".join(body_lines)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0  # fail open

    tool_name = data.get("tool_name") or ""
    if tool_name not in ("Bash", "PowerShell", "Read", "Edit", "Write", "MultiEdit"):
        return 0

    result = data.get("tool_response") or data.get("tool_result") or {}
    if isinstance(result, dict):
        output_str = ""
        for key in ("stdout", "stderr", "output", "content", "text", "result"):
            val = result.get(key)
            if isinstance(val, str):
                output_str += val + "\n"
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        output_str += item["text"] + "\n"
                    elif isinstance(item, str):
                        output_str += item + "\n"
    elif isinstance(result, str):
        output_str = result
    else:
        return 0

    if not output_str or len(output_str) < 20:
        return 0

    hits = set()
    if TRUNCATED.search(output_str):
        hits.add("truncated")
    if NATIVE_ERROR.search(output_str):
        hits.add("native_error")
    if NO_CONTENT.search(output_str):
        hits.add("no_content")
    if CANCELLED_SIBLING.search(output_str):
        hits.add("cancelled_sibling")
    if TOKEN_ECHO.search(output_str):
        hits.add("token_echo")
    if check_mojibake(output_str):
        hits.add("mojibake")
    if check_duplication(output_str):
        hits.add("duplication")

    if not hits:
        return 0

    # Once-per-hit-type-per-session latch (avoids nagging on later calls)
    try:
        sid = str(data.get("session_id") or "unknown")
        sid = re.sub(r"[^\w.-]", "_", sid)[:80]
        d = os.path.join(os.path.expanduser("~"), ".claude", "tmp", "fabrication-guard")
        os.makedirs(d, exist_ok=True)
        marker = os.path.join(d, "hits-%s.txt" % sid)
        already = set()
        if os.path.exists(marker):
            with open(marker, encoding="utf-8") as f:
                already = set(f.read().splitlines())
        fresh = hits - already
        if not fresh:
            return 0
        with open(marker, "a", encoding="utf-8") as f:
            for h in fresh:
                f.write(h + "\n")
        hits = fresh
    except Exception:
        pass  # fail open on latch bug

    print(build_warning(hits, tool_name), file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)  # fail open
