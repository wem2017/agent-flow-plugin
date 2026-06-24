#!/usr/bin/env bash
# Mirror an issue's flow:* state onto the Projects v2 board (human mirror only).
# Adds the issue to the board (idempotent) and sets its Status single-select option.
# Usage: mirror-label-to-board.sh <board_id> <issue_node_id> <status_field_id> <option_id>
#   board_id        PVT_…              (board.id)
#   issue_node_id   from: gh issue view <n> --json id -q .id
#   status_field_id the Status field id (PVTSSF_…)
#   option_id       the option id whose name == board.columns.<key> for the target flow state
# Best-effort: run AFTER the label swap, never instead of it. On error, log and continue.
# Requires: gh authenticated with `project` scope.
set -euo pipefail

board_id="${1:?board_id (PVT_…) required}"
issue_node_id="${2:?issue node id required}"
field_id="${3:?status field id required}"
option_id="${4:?status option id required}"

# 1. add the issue to the project (idempotent — returns the existing item if already added)
item_id="$(gh api graphql -f query='
  mutation($project:ID!, $content:ID!){
    addProjectV2ItemById(input:{ projectId:$project, contentId:$content }){ item { id } }
  }' -F project="$board_id" -F content="$issue_node_id" \
  --jq '.data.addProjectV2ItemById.item.id')"

# 2. set its Status to the target option
gh api graphql -f query='
  mutation($project:ID!, $item:ID!, $field:ID!, $option:String!){
    updateProjectV2ItemFieldValue(input:{
      projectId:$project, itemId:$item, fieldId:$field,
      value:{ singleSelectOptionId:$option }
    }){ projectV2Item { id } }
  }' -F project="$board_id" -F item="$item_id" \
     -F field="$field_id" -F option="$option_id" \
  --jq '.data.updateProjectV2ItemFieldValue.projectV2Item.id' >/dev/null

echo "mirrored: item $item_id → option $option_id"
