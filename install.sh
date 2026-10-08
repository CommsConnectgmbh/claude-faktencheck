#!/usr/bin/env bash
#
# install.sh — installiert claude-faktencheck nach ~/.claude
#
#   skill:  faktencheck          (Belegpflicht-Modus, per /faktencheck)
#   agent:  faktenpruefer        (unabhängiger Prüfer mit frischem Kontext)
#   hooks:  paket-check.py       (PreToolUse/Bash: erfundene Pakete abfangen)
#           beleg-stopp.py       (Stop: kein "fertig" ohne Prüflauf)
#
#   ./install.sh               interaktiv, zeigt Diffs vor dem Überschreiben
#   ./install.sh --yes         ohne Rückfragen
#   ./install.sh --no-hooks    nur Skill und Agent
#   ./install.sh --uninstall   alles wieder entfernen (settings.json bleibt sonst unangetastet)
#
# settings.json wird vorher als settings.json.bak-faktencheck gesichert.

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
    -h|--help)   sed -n '2,17p' "$0"; exit 0 ;;
    *) echo "Unbekannte Option: $arg" >&2; exit 1 ;;
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

command -v python3 >/dev/null || { echo "python3 wird gebraucht (für die Hooks)." >&2; exit 1; }

# settings_hooks add|remove — trägt die Hooks idempotent in settings.json ein oder aus.
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
    || { echo "$SETTINGS ist kein gültiges JSON. Bitte erst reparieren." >&2; exit 1; }
  cp "$SETTINGS" "$SETTINGS.bak-faktencheck"
  ok "Sicherung: $SETTINGS.bak-faktencheck"
}

if [[ "$UNINSTALL" == "1" ]]; then
  sec "claude-faktencheck entfernen"
  backup_settings
  settings_hooks remove
  rm -rf "$HOOK_DIR" "$CLAUDE_DIR/skills/faktencheck" "$CLAUDE_DIR/agents/faktenpruefer.md"
  ok "Hooks, Skill und Agent entfernt."
  exit 0
fi

# copy_file <quelle> <ziel> <label>
copy_file() {
  local src="$1" dst="$2" label="$3"
  if [[ -f "$dst" ]]; then
    if diff -q "$dst" "$src" >/dev/null 2>&1; then ok "$label ist aktuell."; return; fi
    say "  Unterschiede bei $label:"; diff -u "$dst" "$src" || true
    ask "  $label überschreiben?" || { warn "$label übersprungen."; return; }
  fi
  mkdir -p "$(dirname "$dst")"
  cp "$src" "$dst"
  ok "$label installiert."
}

sec "Skill und Agent"
copy_file "$SRC_DIR/skills/faktencheck/SKILL.md" "$CLAUDE_DIR/skills/faktencheck/SKILL.md" "Skill faktencheck"
copy_file "$SRC_DIR/agents/faktenpruefer.md" "$CLAUDE_DIR/agents/faktenpruefer.md" "Agent faktenpruefer"

if [[ "$NO_HOOKS" != "1" ]]; then
  sec "Hooks"
  say "  paket-check: prüft vor npm/pip/cargo-Installationen, ob es das Paket wirklich gibt."
  say "  beleg-stopp: hält \"fertig\" an, wenn Code geändert, aber nicht geprüft wurde."
  if ask "  Hooks installieren und in $SETTINGS eintragen?"; then
    copy_file "$SRC_DIR/hooks/paket-check.py" "$HOOK_DIR/paket-check.py" "Hook paket-check"
    copy_file "$SRC_DIR/hooks/beleg-stopp.py" "$HOOK_DIR/beleg-stopp.py" "Hook beleg-stopp"
    chmod +x "$HOOK_DIR"/*.py
    backup_settings
    settings_hooks add
    ok "Hooks in settings.json eingetragen."
  else
    warn "Hooks übersprungen."
  fi
fi

sec "Fertig"
say "  In Claude Code: /faktencheck  (Belegpflicht an), \"Faktencheck aus\" (wieder aus)"
say "  Prüfer: \"Lass den faktenpruefer über die Antwort laufen\""
say "  Optional: templates/CLAUDE.faktencheck.md in deine CLAUDE.md übernehmen."
say "  Neue Claude-Code-Sitzung starten, damit Hooks und Skill geladen werden."
