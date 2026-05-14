#!/usr/bin/env bash
set -e
cd /home/kiu/bigdem/versus
. /home/kiu/.config/pulse-sre/env
unset ANTHROPIC_API_KEY

OPEN=$(gh issue list --repo kiukairor/bigdem --label sre-remediate --state open --json number --jq 'length' 2>/dev/null || echo 0)
if [ "$OPEN" -eq 0 ]; then
  echo "No open sre-remediate issues. Exiting."
  exit 0
fi

/home/kiu/.local/bin/claude \
  -p "$(cat /home/kiu/bigdem/versus/SRE_AGENT.md)" \
  --dangerously-skip-permissions \
  --output-format text
