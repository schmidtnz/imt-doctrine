#!/usr/bin/env bash
# One-off GitHub settings; needs gh logged in with admin rights on the repo.
set -euo pipefail
repo="${1:-schmidtnz/imt-doctrine}"

gh repo edit "$repo" --enable-auto-merge --enable-discussions --delete-branch-on-merge
gh api -X POST "repos/$repo/rulesets" --input "$(dirname "$0")/../.github/rulesets/main.json" >/dev/null
gh api -X POST "repos/$repo/pages" -f "source[branch]=gh-pages" -f "source[path]=/" >/dev/null \
  || echo "Pages not enabled: needs a public repo or GitHub Pro, and the gh-pages branch from the first publish run."
echo "Done: auto-merge, discussions, ruleset."
