#!/usr/bin/env bash
# Repository settings; needs gh with admin rights and is safe to rerun.
set -euo pipefail
repo="${1:-schmidtnz/imt-doctrine}"
dir="$(dirname "$0")/../.github"

gh repo edit "$repo" --enable-auto-merge --enable-discussions --delete-branch-on-merge
# Read-only Actions token that can't approve pull requests.
gh api -X PUT "repos/$repo/actions/permissions/workflow" -f default_workflow_permissions=read \
  -F can_approve_pull_request_reviews=false
gh label create preview -R "$repo" --color 0E8A16 --force \
  --description "Publish a preview for a pull request from a fork" >/dev/null
# Add or update each ruleset; only admins and Actions workflows may change v* tags.
for file in "$dir/rulesets/main.json" "$dir/rulesets/tags.json"; do
  name=$(grep -m1 '"name"' "$file" | cut -d'"' -f4)
  id=$(gh api "repos/$repo/rulesets?includes_parents=false" --jq ".[] | select(.name == \"$name\") | .id") || id=""
  if [ -n "$id" ]; then
    gh api -X PUT "repos/$repo/rulesets/$id" --input "$file" >/dev/null || echo "Ruleset '$name' not updated."
  else
    gh api -X POST "repos/$repo/rulesets" --input "$file" >/dev/null \
      || echo "Ruleset '$name' not added: rulesets need a public repo or GitHub Pro."
  fi
done
# Published releases (tag and assets) can't then be changed or deleted.
gh api -X PUT "repos/$repo/immutable-releases" >/dev/null || echo "Immutable releases not enabled."
gh api "repos/$repo/pages" >/dev/null 2>&1 \
  || gh api -X POST "repos/$repo/pages" -f "source[branch]=gh-pages" -f "source[path]=/" >/dev/null \
  || echo "Pages not enabled: needs a public repo or GitHub Pro, and the gh-pages branch from the first publish run."
echo "Done: auto-merge, discussions, workflow permissions, preview label, rulesets, immutable releases, Pages."
