# Pulse SRE Agent — Raspberry Pi Setup
# Claude Code polls GitHub every minute for sre-remediate issues

# ── Prerequisites ────────────────────────────────────────────────────────────
# 1. Claude Code installed:
#      npm install -g @anthropic-ai/claude-code
#
# 2. GitHub CLI installed and authenticated:
#      sudo apt install gh
#      gh auth login
#
# 3. Create env file (keeps GH token out of crontab and process list):
#      mkdir -p ~/.config/pulse-sre
#      cat > ~/.config/pulse-sre/env << 'EOF'
#      export GH_TOKEN=ghp_...    # needs issues: write, contents: write
#      EOF
#      chmod 600 ~/.config/pulse-sre/env
#      NOTE: Do NOT set ANTHROPIC_API_KEY here — Claude Code must use the
#      OAuth session (claude login) so it runs on the Pro plan, not the API.
#
# 4. Create GitHub labels (one-time):
#      gh label create sre-remediate --color E11D48 --repo kiukairor/bigdem
#      gh label create sre-resolved  --color 16A34A --repo kiukairor/bigdem

# ── Crontab entry (crontab -e) ───────────────────────────────────────────────
# Runs every minute. Silent when no issue exists. Logs only when it acts.
# flock prevents concurrent runs if remediation takes > 1 min.

* * * * * flock -n /tmp/pulse-sre-agent.lock \
  bash -c '. ~/.config/pulse-sre/env && cd /home/kiu/bigdem/versus && \
  claude -p "$(cat SRE_AGENT.md)" \
    --dangerously-skip-permissions \
    --output-format text' \
  >> /home/kiu/pulse-sre-agent.log 2>&1

# ── What each flag does ──────────────────────────────────────────────────────
# flock -n                         Non-blocking lock. If agent is still running
#                                  from last minute, skip this invocation.
# --dangerously-skip-permissions   No confirmation prompts. Fully autonomous.
# --output-format text             Clean stdout, no JSON wrapper.
# SRE_AGENT.md                     The agent instructions (this repo).
#                                  Claude Code also auto-reads CLAUDE.md for
#                                  full project context — both are active.
# >> ~/pulse-sre-agent.log         Append. Silent when nothing to do
#                                  (SRE_AGENT.md exits silently on empty issues).

# ── IMPORTANT: bug must be introduced via git commit, not kubectl set env ────
# NR Workflow Automation correlates alerts to deployment SHAs from git history.
# kubectl set env leaves no commit — NR cannot correlate it.
# Use the demos/sources/ file-copy + git push approach for the SRE demo,
# NOT trigger_ai_slowness.sh (which uses kubectl set env).
#
# Correct trigger for NR Workflow demo:
#   cp demos/sources/ai-svc-main-bug-ai-slow.py services/ai-svc/main.py
#   git add services/ai-svc/main.py
#   git commit -m "fix: disable recommendation cache to prevent stale AI responses"
#   git push origin main
# NR correlates this SHA when the latency alert fires, puts it in the issue body.
# Claude Code then reverts and properly fixes that exact SHA.

# ── Log rotation (/etc/logrotate.d/pulse-sre-agent) ─────────────────────────
# /home/kiu/pulse-sre-agent.log {
#     daily
#     rotate 7
#     compress
#     missingok
#     notifempty
# }

# ── Verify it's working ──────────────────────────────────────────────────────
# tail -f ~/pulse-sre-agent.log
# gh issue list --label sre-remediate --state open --repo kiukairor/bigdem
