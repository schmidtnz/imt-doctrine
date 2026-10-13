# IMT Doctrine (demonstration)

A working demonstration of writing, reviewing and publishing land SAR IMT doctrine from Git. The structure and numbering follow draft v0.1 (Parts 1–3, forms). The text is condensed from the draft for illustration and is not agreed doctrine.

## What it shows

| Feature | Where |
|---|---|
| Two review tiers: doctrine owners approve Parts 1, 2, 3.1–3.2; anyone approves guidance and forms | `.github/CODEOWNERS`, `.github/rulesets/main.json` |
| Traceability: principle → concept → guideline → process → form, with stale, orphan, coverage and overdue checks | `tools/doctrace.py`, `docs/status/traceability` page |
| Trace box on every item page (parent, children, version, review state) | `docs/_ext/traceability.py` |
| Say it once: shared snippet (POD scale), glossary, organisation-name substitution | `docs/_snippets/`, `docs/glossary.md`, `docs/conf.py` |
| Versioned releases with PDF and zipped HTML | `.github/workflows/release.yml` |
| PR previews, link checking, monthly review-date issue | `.github/workflows/` |

The demo content deliberately contains one stale item (CON-02), one coverage gap (PRN-15) and one overdue review (GDL-04), so the status page has something to show.

## Item metadata

```yaml
---
id: PRC-02
type: process
title: Extended search planning cycle
version: 1
derives_from:        # parent ID: parent version this item was written against
  CON-16: 1
  GDL-05: 1
requires_children: [form]
owner: doctrine-group
last_reviewed: 2026-10-01
---
```

Bump `version` when an item's meaning changes. Children written against the older version are listed as stale until someone reviews them and updates their `derives_from` number.

## Build locally

```sh
pip install -r requirements.txt
pytest -q
python tools/doctrace.py --root docs
sphinx-build -W -b html docs docs/_build/html
```

## First-time setup

1. Push `main`, then run `tools/setup-repo.sh` (needs `gh` with admin rights). It turns on auto-merge and Discussions, adds the ruleset and enables Pages from the `gh-pages` branch.
2. Tag a release: `git tag v0.1.0-demo && git push --tags`.

While the repository is private on GitHub Free, rulesets and Pages are unavailable. CI still runs, and each run's built site is downloadable as the `site` artifact. Both work once the repository is public (or on GitHub Pro).

When the repository moves to an organisation, replace `@schmidtnz` in `CODEOWNERS` with the review group's team.

## Licence

| Material | Licence |
|---|---|
| Code and configuration (`tools/`, `tests/`, `docs/_ext/`, `docs/_static/`, `docs/conf.py`, `.github/`) | [MIT](LICENSE) |
| Doctrine content (everything else under `docs/`) | [CC BY 4.0](LICENSE-docs), pending confirmation by LandSAR |

The doctrine text is condensed from LandSAR's draft v0.1 and remains LandSAR's copyright. Until LandSAR confirms CC BY 4.0, the content is all rights reserved and shared for review only. Only doctrine published by LandSAR is authoritative; adapted copies must not present themselves as official. Third-party figures and forms are not covered by CC BY 4.0. See [NOTICE](NOTICE) for details.
