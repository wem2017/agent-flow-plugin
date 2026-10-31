#!/bin/bash
# Chạy eval trên bản sao tạm có defaultEnabled: true. Manifest thật giữ false để plugin không tự chạy ở repo chưa đồng ý,
# nhưng cờ đó cũng làm sandbox của `claude plugin eval` chạy KHÔNG có plugin. Mọi tham số được chuyển cho eval.
set -euo pipefail
SRC="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cp -R "$SRC" "$TMP/agentflow"
rm -rf "$TMP/agentflow/evals/results"
python3 -I - "$TMP/agentflow/.claude-plugin/plugin.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as fh:
    meta = json.load(fh)
meta["defaultEnabled"] = True
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    json.dump(meta, fh, ensure_ascii=False, indent=2)
PY
OUT="$SRC/evals/results/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT"
KEEP_AWAKE=""
command -v caffeinate >/dev/null && KEEP_AWAKE="caffeinate -i"  # máy ngủ làm phiên chạy đứng mà timeout vẫn tính
$KEEP_AWAKE claude plugin eval "$TMP/agentflow" --scaffold --allow-tools Bash --ablation none --no-publish --trust-plugin \
  --output-dir "$OUT" --report "$OUT/report.html" "$@" < /dev/null
