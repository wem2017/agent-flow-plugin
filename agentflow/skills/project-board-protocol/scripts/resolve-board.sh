#!/usr/bin/env bash
# Resolve a GitHub Projects v2 board NUMBER to its PVT_ node id.
# Usage: resolve-board.sh <owner> <org|user> <number>
# Prints the node id (PVT_…) to stdout, or exits non-zero with an error on stderr.
# Requires: gh authenticated with `project` (+ `read:org` for orgs) scope.
set -euo pipefail

owner="${1:?owner required}"
owner_type="${2:?owner_type required: org|user}"
number="${3:?project number required}"

case "$owner_type" in
  org)  root="organization" ;;
  user) root="user" ;;
  *) echo "owner_type must be 'org' or 'user', got '$owner_type'" >&2; exit 2 ;;
esac

id="$(gh api graphql -f query="
  query(\$login:String!, \$number:Int!){
    ${root}(login:\$login){ projectV2(number:\$number){ id title } }
  }" -F login="$owner" -F number="$number" \
  --jq ".data.${root}.projectV2.id")"

if [ -z "$id" ] || [ "$id" = "null" ]; then
  echo "No Projects v2 board #$number found under $owner_type '$owner' (check scope + number)." >&2
  exit 1
fi
echo "$id"
