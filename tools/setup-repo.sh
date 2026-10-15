#!/usr/bin/env bash
# Repository settings; needs gh with admin rights and is safe to rerun.
set -euo pipefail
# --solo: pull requests need passing checks but no approval, for a lone maintainer.
solo=false
[ "${1:-}" = --solo ] && { solo=true; shift; }
repo="${1:-schmidtnz/imt-doctrine}"
dir="$(dirname "$0")/../.github"
failed=0
warn() { echo "$*"; failed=1; }

gh repo edit "$repo" --enable-auto-merge --enable-discussions --delete-branch-on-merge
# Read-only Actions token that can't approve pull requests.
gh api -X PUT "repos/$repo/actions/permissions/workflow" -f default_workflow_permissions=read \
  -F can_approve_pull_request_reviews=false
gh label create preview -R "$repo" --color 0E8A16 --force \
  --description "Publish a preview for a pull request from a fork" >/dev/null
# Only admins and the release app may change v* tags.
app_id=$(gh variable get RELEASE_APP_ID -R "$repo" 2>/dev/null) || app_id=""
for file in "$dir/rulesets/main.json" "$dir/rulesets/tags.json"; do
  name=$(grep -m1 '"name"' "$file" | cut -d'"' -f4)
  if grep -q '"RELEASE_APP_ID"' "$file" && [ -z "$app_id" ]; then
    warn "Ruleset '$name' skipped: set the RELEASE_APP_ID variable first."; continue
  fi
  body=$(sed "s/\"RELEASE_APP_ID\"/$app_id/" "$file")
  if $solo; then
    body=$(echo "$body" | sed -e 's/"required_approving_review_count": 1/"required_approving_review_count": 0/' \
      -e 's/"require_code_owner_review": true/"require_code_owner_review": false/' \
      -e 's/"require_last_push_approval": true/"require_last_push_approval": false/')
  fi
  id=$(gh api "repos/$repo/rulesets?includes_parents=false" --jq ".[] | select(.name == \"$name\") | .id") || id=""
  if [ -n "$id" ]; then
    out=$(echo "$body" | gh api -X PUT "repos/$repo/rulesets/$id" --input - 2>&1) || warn "Ruleset '$name' not updated: $out"
  else
    out=$(echo "$body" | gh api -X POST "repos/$repo/rulesets" --input - 2>&1) || warn "Ruleset '$name' not added: $out"
  fi
done
# Published releases (tag and assets) can't then be changed or deleted.
gh api -X PUT "repos/$repo/immutable-releases" >/dev/null || warn "Immutable releases not enabled."
gh api "repos/$repo/pages" >/dev/null 2>&1 \
  || gh api -X POST "repos/$repo/pages" -f "source[branch]=gh-pages" -f "source[path]=/" >/dev/null \
  || warn "Pages not enabled: needs a public repo or GitHub Pro, and the gh-pages branch from the first publish run."
[ "$failed" = 0 ] && echo "Done." || { echo "Done, except as noted above."; exit 1; }
