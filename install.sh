#!/usr/bin/env bash
#
# install.sh: install claude-faktencheck into ~/.claude
#
#   skill:  faktencheck          (evidence-required mode, via /faktencheck)
#   agent:  faktenpruefer        (independent reviewer with fresh context)
#   hooks:  paket-check.py       (PreToolUse/Bash: catch invented packages)
#           beleg-stopp.py       (Stop: no "done" without a check)
#
#   ./install.sh               interactive, shows diffs before overwriting
#   ./install.sh --yes         no prompts
#   ./install.sh --no-hooks    skill and agent only
#   ./install.sh --uninstall   remove installed components (otherwise leave settings.json unchanged)
#
# settings.json is backed up to settings.json.bak-faktencheck before changes.

set -euo pipefail

CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK_DIR="$CLAUDE_DIR/hooks/faktencheck"
SETTINGS="$CLAUDE_DIR/settings.json"

ASSUME_YES=""; NO_HOOKS=""; UNINSTALL=""
for arg in "$@"; do
  case "$arg" in
    --yes|-y)    ASSUME_YES=1 ;;
    --no-hooks)  NO_HOOKS=1 ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help)   sed -n '3,15p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

if [[ -t 1 ]]; then
  GREEN=$'\033[0;32m'; CYAN=$'\033[0;36m'; YELLOW=$'\033[0;33m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
else
  GREEN=""; CYAN=""; YELLOW=""; BOLD=""; RESET=""
fi
say()  { printf "%s\n" "$*"; }
sec()  { printf "\n%s%s%s\n" "$BOLD" "$*" "$RESET"; }
ok()   { printf "  %s✓%s %s\n" "$GREEN" "$RESET" "$*"; }
warn() { printf "  %s!%s %s\n" "$YELLOW" "$RESET" "$*"; }
ask()  { [[ "$ASSUME_YES" == "1" ]] && return 0; printf "%s?%s %s [y/N] " "$CYAN" "$RESET" "$*"; read -r r; [[ "$r" =~ ^[Yy]$ ]]; }

command -v python3 >/dev/null || { echo "python3 is required (for the hooks)." >&2; exit 1; }

# settings_hooks add|remove: add or remove hooks in settings.json idempotently.
settings_hooks() {
  python3 - "$1" "$SETTINGS" "$HOOK_DIR" <<'PY'
import json, os, shlex, sys
mode, path, hook_dir = sys.argv[1:4]
ours = {
    "PreToolUse": ("Bash", shlex.quote(os.path.join(hook_dir, "paket-check.py")), 15),
    "Stop": (None, shlex.quote(os.path.join(hook_dir, "beleg-stopp.py")), 10),
}
own = {os.path.join(hook_dir, f) for f in ("paket-check.py", "beleg-stopp.py")}
data = {}
if os.path.exists(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
hooks = data.setdefault("hooks", {})
for event, (matcher, cmd, timeout) in ours.items():
    groups = hooks.get(event, [])
    kept = []
    for g in groups:
        g["hooks"] = [h for h in g.get("hooks", []) if h.get("command", "").strip("'\"") not in own]
        if g["hooks"]:
            kept.append(g)
    if mode == "add":
        entry = {"hooks": [{"type": "command", "command": cmd, "timeout": timeout}]}
        if matcher:
            entry["matcher"] = matcher
        kept.append(entry)
    if kept:
        hooks[event] = kept
    else:
        hooks.pop(event, None)
if not hooks:
    data.pop("hooks", None)
if data or os.path.exists(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)
PY
}

backup_settings() {
  [[ -f "$SETTINGS" ]] || return 0
  python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$SETTINGS" 2>/dev/null \
    || { echo "$SETTINGS is not valid JSON. Please fix it first." >&2; exit 1; }
  cp "$SETTINGS" "$SETTINGS.bak-faktencheck"
  ok "Backup: $SETTINGS.bak-faktencheck"
}

if [[ "$UNINSTALL" == "1" ]]; then
  sec "Uninstall claude-faktencheck"
  backup_settings
  settings_hooks remove
  rm -rf "$HOOK_DIR" "$CLAUDE_DIR/skills/faktencheck" "$CLAUDE_DIR/agents/faktenpruefer.md"
  ok "Hooks, skill, and agent removed."
  exit 0
fi

# copy_file <source> <destination> <label>
copy_file() {
  local src="$1" dst="$2" label="$3"
  if [[ -f "$dst" ]]; then
    if diff -q "$dst" "$src" >/dev/null 2>&1; then ok "$label is up to date."; return; fi
    say "  Differences for $label:"; diff -u "$dst" "$src" || true
    ask "  Overwrite $label?" || { warn "$label skipped."; return; }
  fi
  mkdir -p "$(dirname "$dst")"
  cp "$src" "$dst"
  ok "$label installed."
}

sec "Skill and agent"
copy_file "$SRC_DIR/skills/faktencheck/SKILL.md" "$CLAUDE_DIR/skills/faktencheck/SKILL.md" "Skill faktencheck"
copy_file "$SRC_DIR/agents/faktenpruefer.md" "$CLAUDE_DIR/agents/faktenpruefer.md" "Agent faktenpruefer"

if [[ "$NO_HOOKS" != "1" ]]; then
  sec "Hooks"
  say "  paket-check: checks whether packages exist before npm/pip/cargo installations."
  say "  beleg-stopp: pauses \"done\" if code was changed without a check."
  if ask "  Install hooks and add them to $SETTINGS?"; then
    copy_file "$SRC_DIR/hooks/paket-check.py" "$HOOK_DIR/paket-check.py" "Hook paket-check"
    copy_file "$SRC_DIR/hooks/beleg-stopp.py" "$HOOK_DIR/beleg-stopp.py" "Hook beleg-stopp"
    chmod +x "$HOOK_DIR"/*.py
    backup_settings
    settings_hooks add
    ok "Hooks added to settings.json."
  else
    warn "Hooks skipped."
  fi
fi

sec "Done"
say "  In Claude Code: /faktencheck (require evidence), \"fact check off\" or \"Faktencheck aus\" (turn it off)"
say "  Reviewer: \"Ask faktenpruefer to check the response\""
say "  Optional: add templates/CLAUDE.faktencheck.md to your CLAUDE.md."
say "  Start a new Claude Code session to load the hooks and skill."
