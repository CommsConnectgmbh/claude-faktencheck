#!/usr/bin/env bash
# Replays what Claude Code does before a Bash call: it hands the command to
# hooks/paket-check.py. The hook output below is real (live registry lookups).
HOOK="$(cd "$(dirname "$0")/../.." && pwd)/hooks/paket-check.py"
run() {
  printf '\033[2m● Claude wants to run:\033[0m \033[1m%s\033[0m\n' "$1"
  sleep 0.6
  if out=$(printf '{"tool_name":"Bash","tool_input":{"command":%s},"cwd":"/tmp"}' "$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$1")" | python3 "$HOOK" 2>&1); then
    printf '\033[32m  ✓ paket-check: ok, command runs\033[0m\n\n'
  else
    printf '\033[31m  ✗ blocked by paket-check\033[0m\n'
    printf '%s\n' "$out" | sed -n '2,2p' | sed 's/^/  /'
    printf '\033[2m  Claude gets this message and has to check the name first.\033[0m\n\n'
  fi
  sleep 1.6
}
clear
printf '\033[1;36mclaude-faktencheck\033[0m  catching invented packages before install\n\n'
sleep 1
run "npm install express"
run "pip install fastapi-auth-middleware-pro"
run "npm install react-native-smart-forms-validator"
run "cargo add serde_json"
sleep 1.5
