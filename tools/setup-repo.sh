#!/usr/bin/env bash
# One-off GitHub settings; needs gh logged in with admin rights on the repo.
set -euo pipefail
repo="${1:-schmidtnz/imt-doctrine}"

gh repo edit "$repo" --enable-auto-merge --enable-discussions --delete-branch-on-merge
gh api -X PUT "repos/$repo/actions/permissions/workflow" -f default_workflow_permissions=read \
  -F can_approve_pull_request_reviews=true  # lets Prepare release open its pull request
gh label create preview -R "$repo" --color 0E8A16 --force \
  --description "Publish a preview for a pull request from a fork" >/dev/null
for ruleset in main tags; do
  gh api -X POST "repos/$repo/rulesets" --input "$(dirname "$0")/../.github/rulesets/$ruleset.json" >/dev/null \
    || echo "Ruleset '$ruleset' not added: needs a public repo or GitHub Pro."
done
# Published releases (tag and assets) can't then be changed or deleted.
gh api -X PUT "repos/$repo/immutable-releases" >/dev/null || echo "Immutable releases not enabled."
gh api -X POST "repos/$repo/pages" -f "source[branch]=gh-pages" -f "source[path]=/" >/dev/null \
  || echo "Pages not enabled: needs a public repo or GitHub Pro, and the gh-pages branch from the first publish run."
echo "Done: auto-merge, discussions, Actions pull requests, preview label, rulesets, immutable releases."
