#!/usr/bin/env python3
"""Stop hook: no "done" without evidence.

Read the transcript from the last genuine user message and pause the end
of the turn once if

  1. Code was changed (Edit/Write/NotebookEdit) without a subsequent check
     of the change (test, build, lint, script, curl, browser), or
  2. The final response claims success ("tests pass", "verified",
     "is live", "all tests pass" ...), but no check ran during the turn.

Claude is prompted to verify the claim or retract it.
`stop_hook_active` prevents a loop: at most one prompt per turn.
Disable with the environment variable `FAKTENCHECK_AUS=1`. All errors fail open.
"""
import json
import os
import re
import shlex
import sys

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
CODE_EXT = re.compile(
    r"\.(tsx?|jsx?|mjs|cjs|py|swift|kts?|java|sql|go|rs|rb|php|css|scss|html|vue|svelte|astro|sh|zsh|"
    r"ps1|ya?ml|toml|c|cc|cpp|h|hpp|cs|dart|ex|exs|lua)$"
)
# Programs whose invocation counts as a check. Inspect the program at the start
# of each simple command, not a word anywhere in it: `echo pytest`
# and `cat npm.log` do not check anything.
CHECK_PROGRAMS = {
    "test", "pytest", "py.test", "tox", "nox", "vitest", "jest", "mocha", "playwright", "cypress",
    "tsc", "eslint", "ruff", "mypy", "pyright", "flake8", "pylint", "shellcheck", "biome", "prettier",
    "npm", "npx", "pnpm", "pnpx", "yarn", "bun", "bunx", "node", "deno", "python", "python3", "uv", "uvx",
    "poetry", "cargo", "go", "swift", "xcodebuild", "gradle", "gradlew", "mvn", "dotnet", "make", "cmake",
    "ctest", "bazel", "php", "phpunit", "composer", "ruby", "rspec", "rake", "bundle", "mix", "elixir",
    "curl", "wget", "http", "docker", "kubectl", "terraform", "bash", "sh", "zsh",
}
WRAPPERS = {"sudo", "env", "time", "nice", "nohup", "command", "exec", "doas"}
WRAPPER_VALUE_FLAGS = {"-u", "-g", "-C", "-D", "-h", "-p", "-U", "-r", "-t", "-T", "-S", "--user", "--group",
                       "--chdir", "--adjustment"}

CHECK_SKILLS = {"run", "verify", "canary", "code-review", "second-opinion", "webapp-testing"}
CLAIM = re.compile(
    r"(tests?\s+(sind\s+|laufen\s+|are\s+)?(alle\s+)?(gr(ü|ue)n|bestanden|durch|pass(ed|ing)?)|"
    r"all\s+tests\s+pass|"
    r"\b(erfolgreich\s+)?(getestet|verifiziert|verified|tested)\b|"
    r"\bist\s+(jetzt\s+)?live\b|\bis\s+(now\s+)?live\b|"
    r"erfolgreich\s+deploy|successfully\s+deployed|"
    r"funktioniert\s+(jetzt|wieder|einwandfrei)|works\s+(now|correctly))",
    re.I,
)


HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n.*?^\s*\1\s*$", re.S | re.M)


def simple_commands(command):
    """Split a Bash command into simple commands; quotes, comments, and here-documents remain text."""
    command = HEREDOC.sub("", command)
    for line in command.splitlines():
        lexer = shlex.shlex(line, posix=False, punctuation_chars=";&|()")
        lexer.whitespace_split = True
        lexer.commenters = "#"
        current = []
        try:
            for token in lexer:
                if set(token) <= set(";&|()"):
                    if current:
                        yield current
                    current = []
                else:
                    current.append(token)
        except ValueError:  # Incomplete quotes, e.g. a multiline string
            continue
        if current:
            yield current


def first_program(words):
    i = 0
    while i < len(words):
        w = words[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w):
            i += 1
        elif os.path.basename(w) in WRAPPERS:
            i += 1
            while i < len(words) and words[i].startswith("-"):
                i += 2 if words[i] in WRAPPER_VALUE_FLAGS else 1
        else:
            return words[i:]
    return []


def runs_check(command):
    """True if a simple command in `command` starts a checking program."""
    for words in simple_commands(command):
        words = first_program(words)
        if not words:
            continue
        program = words[0].strip("'\"")
        prog = os.path.basename(program)
        if prog in {"bash", "sh", "zsh"} and len(words) == 1:
            continue
        if prog in CHECK_PROGRAMS or re.match(r"^\./|.*\.(sh|py|mjs|js|ts)$", program):
            return True
    return False


def check_step(name, inp):
    if name == "Bash":
        return runs_check(inp.get("command", ""))
    if name.startswith(("mcp__playwright__", "mcp__chrome", "mcp__puppeteer")):
        return True
    if name in {"WebFetch"}:
        return True
    if name == "Skill":
        return inp.get("skill", "") in CHECK_SKILLS
    if name in {"Agent", "Task"}:
        return bool(re.search(r"\b(test|pr(ü|ue)f|verif|build|review)", inp.get("prompt", ""), re.I))
    return False


NEGATION = re.compile(
    r"\b(nicht|nie|kein\w*|weder|noch|not|never|neither|nor)\s+((noch|yet|mehr|erfolgreich|richtig|ganz)\s+)?$",
    re.I,
)


def negated(text, start):
    """True if a negation precedes the match ("not tested", "not yet verified")."""
    return bool(NEGATION.search(text[max(0, start - 30):start]))


def real_user_message(entry):
    if entry.get("type") != "user" or entry.get("isSidechain") or entry.get("isMeta"):
        return False
    content = entry.get("message", {}).get("content")
    if isinstance(content, str):
        return True
    return isinstance(content, list) and not any(
        isinstance(c, dict) and c.get("type") == "tool_result" for c in content
    )


def load(path):
    entries = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                entries.append(json.loads(line))
            except ValueError:
                continue
    return entries


def verdict(entries, last_message=None):
    start = max((i for i, e in enumerate(entries) if real_user_message(e)), default=-1)
    calls, last_text = [], ""
    for entry in entries[start + 1:]:
        if entry.get("type") != "assistant" or entry.get("isSidechain"):
            continue
        for block in entry.get("message", {}).get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                calls.append((block.get("name", ""), block.get("input") or {}))
            elif block.get("type") == "text" and block.get("text", "").strip():
                last_text = block["text"]
    last_text = last_message or last_text

    last_edit, edited = -1, ""
    for i, (name, inp) in enumerate(calls):
        path = inp.get("file_path") or inp.get("notebook_path") or ""
        if name in EDIT_TOOLS and CODE_EXT.search(path):
            last_edit, edited = i, path
    if last_edit >= 0 and not any(check_step(n, i) for n, i in calls[last_edit + 1:]):
        return (
            f"Code changed ({os.path.basename(edited)}), but no subsequent command or tool checked the change. "
            "Check it now (test, build, lint, or live check). If you cannot, explain in one sentence "
            "why, then finish."
        )
    claim = next((m for m in CLAIM.finditer(last_text or "") if not negated(last_text, m.start())), None)
    if claim and not any(check_step(n, i) for n, i in calls):
        return (
            f"Your response claims \"{claim.group(0).strip()}\", but no verification step ran during this turn. "
            "Support it now with an actual run (test, build, curl, browser), or retract the claim "
            "and say what remains unchecked."
        )
    return None


def main():
    data = json.load(sys.stdin)
    if data.get("stop_hook_active") or os.environ.get("FAKTENCHECK_AUS") == "1":
        return
    reason = verdict(load(data["transcript_path"]), data.get("last_assistant_message"))
    if reason:
        print(json.dumps({"decision": "block", "reason": reason}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
