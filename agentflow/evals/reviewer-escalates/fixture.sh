#!/bin/bash
# Repo thật, origin là bare repo trong workspace (đường dẫn chứa acme/app để khớp REPO).
set -euo pipefail
export GIT_AUTHOR_DATE="2026-01-01T00:00:00+0000" GIT_COMMITTER_DATE="2026-01-01T00:00:00+0000"  # SHA cố định, mock nhắc được
BARE="$PWD/.origin/github.com/acme/app.git"
mkdir -p "$(dirname "$BARE")"
git init -q --bare -b master "$BARE"
git init -q -b master .
git config user.email t@example.com
git config user.name t
git remote add origin "file://$BARE"
printf '.origin/\n.claude/settings.local.json\n.claude/worktrees/\n.env\n' > .gitignore
cat > agentflow.yaml <<'YAML'
schema: 4
lang: vi
board:
  url: https://github.com/orgs/acme/projects/3
  status: {backlog: Backlog, ready: Ready, in_progress: In Progress, in_review: In Review, in_qc: In QC, ready_to_merge: Ready to Merge, done: Done}
  fields: {size: Size}
classify: label
types: {Feature: feat, Bug: fix}
labels: {agent: agentflow, blocked: blocked, needs_info: needs-info, changes_requested: changes-requested, qc_failed: qc-failed, qc_manual: qc-manual, deploying: deploying}
git: {base: master, protected: [], branch: "{type}/{issue}-{slug}", commit: "{type}: {subject}", link: Closes}
forbidden: []
design: {figma: false, repo: []}
staging: {branch: staging, url: "", build: "", notes: "", timeout_min: 30}
people: {po: [acme-po], qc: [acme-qc], reviewers: [acme-rev]}
run: {parallel: 1, max_tasks: 1, max_review_rounds: 3, max_qc_rounds: 2, models: {dev: {default: sonnet}, reviewer: sonnet, qc: sonnet}}
notify: {telegram: false, events: [blocked]}
YAML
printf 'def add(a, b):\n    return a + b\n' > calc.py
git add -A
git commit -qm "chore: init"
git push -q origin master
git branch staging
git push -q origin staging
git switch -q -c feat/42-chia
printf 'def add(a, b):\n    return a + b\n\n\ndef div(a, b):\n    return a * b\n' > calc.py
git commit -qam "feat: chia"
git push -q -u origin feat/42-chia
git switch -q master
