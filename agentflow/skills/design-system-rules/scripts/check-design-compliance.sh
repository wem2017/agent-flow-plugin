#!/usr/bin/env bash
#
# check-design-compliance.sh — gate cơ học cho design system rules của AgentFlow.
#
# Dùng bởi: skill design-system-rules (DESIGNER trước khi push, và trong design review mode).
#
#   check-design-compliance.sh --staged            # check các file đang staged (pre-push gate của DESIGNER)
#   check-design-compliance.sh --diff <base>       # check diff so với <base> (design review trên PR)
#
# Exit 0 = pass. Exit 1 = có vi phạm; stdout là một list ĐÁNH SỐ paste thẳng được vào
# comment "[DESIGNER] ❌". Exit 2 = lỗi cấu hình (không tìm được config, thiếu tool).
#
# Nó check ĐƯỢC:  diff scope · raw literal (hex/px/font) ngoài token allowlist ·
#                 artifact completeness (spec.md + heading bắt buộc) · rules file tồn tại
# Nó KHÔNG check được: visual fidelity, hierarchy, cân đối, hay design có tốt không.
# Exit 0 KHÔNG phải bằng chứng design đã ổn — nó chỉ nghĩa là phần cơ học sạch.

set -euo pipefail

CONFIG=".claude/agentflow.yaml"
MODE=""
BASE=""

usage() { echo "usage: $0 [--staged | --diff <base>]" >&2; exit 2; }

while [ $# -gt 0 ]; do
  case "$1" in
    --staged) MODE="staged"; shift ;;
    --diff)   MODE="diff"; BASE="${2:-}"; [ -n "$BASE" ] || usage; shift 2 ;;
    -h|--help) usage ;;
    *) echo "unknown arg: $1" >&2; usage ;;
  esac
done
[ -n "$MODE" ] || MODE="staged"

command -v git >/dev/null 2>&1 || { echo "check-design-compliance: cần \`git\`" >&2; exit 2; }
[ -f "$CONFIG" ] || { echo "check-design-compliance: không tìm thấy $CONFIG — chạy từ repo root sau /agentflow-init" >&2; exit 2; }

# ── Đọc config ───────────────────────────────────────────────────────────────
# Dùng `yq` khi có. Khi không có, fallback sang awk: config của AgentFlow nông và
# có shape cố định, nên parse được an toàn mà không cần thêm dependency. Gate này
# phải chạy được ở mọi máy — một enforcement check bị skip vì thiếu tool thì vô dụng.
HAVE_YQ=0
command -v yq >/dev/null 2>&1 && HAVE_YQ=1

# cfg <yq-path> <top-key> <leaf-key>  → giá trị scalar, hoặc "" nếu không có
cfg() {
  if [ "$HAVE_YQ" = "1" ]; then
    yq -r "$1 // \"\"" "$CONFIG" 2>/dev/null || echo ""
  else
    awk -v top="$2" -v leaf="$3" '
      /^[a-zA-Z_]/ { inblk = ($0 ~ "^"top":") ? 1 : 0 }
      inblk && $1 == leaf":" {
        sub(/^[[:space:]]*[a-zA-Z_]+:[[:space:]]*/, "")
        sub(/[[:space:]]*#.*$/, "")
        gsub(/^"|"$/, "")
        print; exit
      }
    ' "$CONFIG"
  fi
}

DESIGN_ENABLED="$(cfg '.design.enabled' design enabled)"
DESIGN_FOLDER="$(cfg '.design.folder'  design folder)"
RULES_FILE="$(cfg '.design.rules_file' design rules_file)"

if [ "$DESIGN_ENABLED" != "true" ]; then
  echo "design.enabled != true — bỏ qua design compliance check."
  exit 0
fi

# Path của các surface có ui: true. Đây là NƠI DUY NHẤT quyết định "file nào là file UI".
if [ "$HAVE_YQ" = "1" ]; then
  UI_PATHS="$(yq -r '.surfaces // {} | to_entries | map(select(.value.ui == true) | .value.path) | .[]' "$CONFIG" 2>/dev/null || true)"
else
  # Gom (path, ui) của từng surface rồi chỉ in path khi ui: true.
  UI_PATHS="$(awk '
    /^[a-zA-Z_]/ { insurf = ($0 ~ /^surfaces:/) ? 1 : 0 }
    insurf && /^  [a-zA-Z_."][^:]*:[[:space:]]*$/ {
      if (path != "" && ui == "true") print path
      path = ""; ui = ""
    }
    insurf && $1 == "path:" { p = $2; gsub(/^"|"$/, "", p); path = p }
    insurf && $1 == "ui:"   { u = $2; sub(/[[:space:]]*#.*$/, "", u); ui = u }
    END { if (path != "" && ui == "true") print path }
  ' "$CONFIG")"
fi

# ── Thu thập file cần check ──────────────────────────────────────────────────
if [ "$MODE" = "staged" ]; then
  FILES="$(git diff --cached --name-only --diff-filter=ACMR || true)"
else
  FILES="$(git diff --name-only --diff-filter=ACMR "$BASE"...HEAD || true)"
fi

if [ -z "$FILES" ]; then
  echo "Không có file nào để check ($MODE)."
  exit 0
fi

FINDINGS=()
add() { FINDINGS+=("$1"); }

# ── Check 4: rules file ──────────────────────────────────────────────────────
# Chạy trước vì check 2 phụ thuộc nó để dựng token allowlist.
if [ -z "$RULES_FILE" ]; then
  add "design.rules_file chưa được khai báo trong $CONFIG — không có nguồn rules ưu tiên #1. Set nó, hoặc scaffold rules file qua /agentflow-init."
elif [ ! -f "$RULES_FILE" ]; then
  add "design.rules_file trỏ tới \`$RULES_FILE\` nhưng file không tồn tại — nguồn ưu tiên #1 đang rỗng."
elif [ ! -s "$RULES_FILE" ]; then
  add "design.rules_file \`$RULES_FILE\` tồn tại nhưng rỗng."
fi

# ── Check 1: diff scope (chỉ ở mode --staged, tức pre-push gate của DESIGNER) ─
# DESIGNER chỉ được ghi vào design folder + rules file. Đây là ranh giới role mà
# tool grant KHÔNG enforce được, nên nó được enforce ở đây.
if [ "$MODE" = "staged" ]; then
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    if [ -n "$DESIGN_FOLDER" ] && [ "${f#"${DESIGN_FOLDER%/}/"}" != "$f" ]; then continue; fi
    if [ -n "$RULES_FILE" ] && [ "$f" = "$RULES_FILE" ]; then continue; fi
    add "\`$f\` nằm ngoài phạm vi ghi của DESIGNER (chỉ \`${DESIGN_FOLDER:-<chưa set>}\` và \`${RULES_FILE:-<chưa set>}\`). App source code là của DEV — unstage file này."
  done <<< "$FILES"
fi

# ── Check 2: raw literal trong file UI ───────────────────────────────────────
# Token allowlist = mọi tên token/biến xuất hiện trong rules file + theme/config
# file của các surface UI. Một literal thô chỉ bị flag khi allowlist KHÔNG rỗng —
# repo chưa có token nào thì flag mọi hex là noise thuần tuý.
ALLOWLIST_SRC=""
[ -n "$RULES_FILE" ] && [ -f "$RULES_FILE" ] && ALLOWLIST_SRC="$RULES_FILE"
while IFS= read -r p; do
  [ -n "$p" ] || continue
  for cand in "$p/tailwind.config.js" "$p/tailwind.config.ts" "$p/tailwind.config.cjs" \
              "$p/theme.js" "$p/theme.ts" "$p/tokens.json" "$p/tokens.css"; do
    [ -f "$cand" ] && ALLOWLIST_SRC="$ALLOWLIST_SRC $cand"
  done
done <<< "$UI_PATHS"

TOKEN_COUNT=0
if [ -n "$ALLOWLIST_SRC" ]; then
  # shellcheck disable=SC2086
  TOKEN_COUNT="$(grep -ohE -- '--[a-zA-Z0-9-]+|\b[a-z]+(-[a-z0-9]+)+\b' $ALLOWLIST_SRC 2>/dev/null | sort -u | wc -l | tr -d ' ')"
fi

is_ui_file() {
  local f="$1"
  case "$f" in *.css|*.scss|*.less|*.tsx|*.jsx|*.vue|*.svelte|*.kt|*.swift) ;; *) return 1 ;; esac
  while IFS= read -r p; do
    [ -n "$p" ] || continue
    [ "$p" = "." ] && return 0
    [ "${f#"${p%/}/"}" != "$f" ] && return 0
  done <<< "$UI_PATHS"
  return 1
}

if [ "$TOKEN_COUNT" -gt 0 ]; then
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    [ -f "$f" ] || continue
    is_ui_file "$f" || continue

    # Hex color thô. Bỏ qua dòng định NGHĨA token (chứa `--x:` hoặc nằm trong file token).
    while IFS=: read -r lineno content; do
      [ -n "$lineno" ] || continue
      case "$content" in *--*:*) continue ;; esac
      add "\`$f:$lineno\` — hex color thô \`$(echo "$content" | grep -oiE '#[0-9a-f]{3,8}' | head -1)\`. Dùng token màu của design system thay vì literal."
    done < <(grep -inE '#[0-9a-f]{3}([0-9a-f]{3}([0-9a-f]{2})?)?\b' "$f" 2>/dev/null | head -20 || true)

    # px thô. 0px và 1px (hairline border) được miễn — chúng gần như không bao giờ là token.
    while IFS=: read -r lineno content; do
      [ -n "$lineno" ] || continue
      case "$content" in *--*:*) continue ;; esac
      add "\`$f:$lineno\` — giá trị px thô \`$(echo "$content" | grep -oE '\b[0-9]+px' | head -1)\`. Dùng token spacing/sizing thay vì literal."
    done < <(grep -inE '\b([2-9]|[1-9][0-9]+)px\b' "$f" 2>/dev/null | head -20 || true)

    # Font stack thô.
    while IFS=: read -r lineno _; do
      [ -n "$lineno" ] || continue
      add "\`$f:$lineno\` — font-family khai báo trực tiếp. Dùng token typography của design system."
    done < <(grep -inE 'font-family\s*:' "$f" 2>/dev/null | head -5 || true)
  done <<< "$FILES"
fi

# ── Check 3: artifact completeness ───────────────────────────────────────────
REQUIRED_HEADINGS=("## Maps to" "## Layout" "## Tokens" "## Components" "## States" "## Responsive" "## Accessibility")
if [ -n "$DESIGN_FOLDER" ] && [ -d "$DESIGN_FOLDER" ]; then
  while IFS= read -r d; do
    [ -n "$d" ] || continue
    slug="$(basename "$d")"
    spec="$d/spec.md"
    if [ ! -f "$spec" ]; then
      add "\`$d\` thiếu \`spec.md\` — DEV không có contract để implement. Xem reference/design-artifacts.md."
      continue
    fi
    for h in "${REQUIRED_HEADINGS[@]}"; do
      grep -qF "$h" "$spec" || add "\`$spec\` thiếu heading bắt buộc \`$h\` (screen \`$slug\`)."
    done
  done < <(find "$DESIGN_FOLDER" -mindepth 1 -maxdepth 1 -type d 2>/dev/null || true)
fi

# ── Report ───────────────────────────────────────────────────────────────────
if [ ${#FINDINGS[@]} -eq 0 ]; then
  echo "Design compliance: PASS (phần cơ học sạch — visual fidelity vẫn cần bạn tự đánh giá)."
  exit 0
fi

echo "Design compliance: FAIL — ${#FINDINGS[@]} vi phạm."
echo
i=1
for f in "${FINDINGS[@]}"; do
  echo "$i. $f"
  i=$((i + 1))
done
exit 1
