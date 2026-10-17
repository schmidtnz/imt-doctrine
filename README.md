# IMT Doctrine (demonstration)

[![CI](https://github.com/schmidtnz/imt-doctrine/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/schmidtnz/imt-doctrine/actions/workflows/ci.yml?query=branch%3Amain) [![Traceability](https://img.shields.io/endpoint?url=https%3A%2F%2Fschmidtnz.github.io%2Fimt-doctrine%2Ftraceability.json)](https://schmidtnz.github.io/imt-doctrine/status/traceability.html) [![Release](https://img.shields.io/github/v/release/schmidtnz/imt-doctrine?include_prereleases)](https://github.com/schmidtnz/imt-doctrine/releases)

A working demonstration of writing, reviewing and publishing land SAR IMT doctrine from Git. The structure and numbering follow draft v0.1 (Parts 1–3, forms). The text is condensed from the draft for illustration and is not agreed doctrine.

**Read it:** <https://schmidtnz.github.io/imt-doctrine/> (latest from `main`, with a [PDF](https://schmidtnz.github.io/imt-doctrine/imt-doctrine.pdf)). To suggest a change, use "Edit this page" on any page; GitHub opens a pull request for you.

## What it shows

| Feature | Where |
|---|---|
| Two review tiers: doctrine owners approve Parts 1, 2, 3.1–3.2; anyone approves guidance and forms | `.github/CODEOWNERS`, `.github/rulesets/main.json` |
| Traceability: principle → concept → guideline → process → form, with stale, orphan, coverage and overdue checks; a comment on each pull request lists the findings it adds or resolves | `tools/doctrace.py`, `docs/status/traceability` page |
| Trace box on every item page (parent, children, version, review state) | `docs/_ext/traceability.py` |
| Say it once: shared snippet (POD scale), glossary, organisation-name substitution | `docs/_snippets/`, `docs/glossary.md`, `docs/conf.py` |
| Figures: SVG diagrams converted to PDF for the printed version, PNG and JPG used as they are; numbered and cross-referenced | `docs/figures/` |
| Releases: version worked out from item changes, changelog from pull request summaries, PDF, zipped HTML and checksums | `tools/release.py`, `.github/workflows/prepare-release.yml`, `release.yml` |
| PR previews with PDF (forks too), link checking, monthly review-date issue | `.github/workflows/` |

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

Needs [uv](https://docs.astral.sh/uv/), which installs Python 3.12 and the dependencies on first use.

```sh
uv run pytest -q
uv run python tools/doctrace.py --root docs
uv run sphinx-build -W -b html docs docs/_build/html
```

`uv.lock` pins every package so a release can be rebuilt exactly. Change dependencies with `uv add` or `uv remove` (`--dev` for test-only ones), which update `pyproject.toml` and the lock together. Dependabot proposes updates monthly.

## Releasing

1. Every pull request ends with a **Changelog summary**: a sentence or two for readers, or "none". Reviewers can reword it before merging.
2. After each merge to `main`, **Prepare release** keeps one "Release vX.Y.Z" pull request up to date. It works out the version and writes the changelog section. Each entry credits its pull request's author, and the section lists everyone who wrote or co-wrote a change, by their GitHub profile name or else their handle. Newcomers are added to the overall `docs/contributors.md` page, which also takes people added by hand. Automatic runs use the `RELEASE_CHANNEL` repository variable (default demo) and open a pull request only when there is something for the changelog. To choose final, rc (release candidate for consultation) or a higher bump, a doctrine owner runs **Actions → Prepare release** by hand; later merges keep that choice.
3. Reword the section in that pull request if needed, then approve and merge. The next merge to `main` rebuilds the section, so reword just before merging. **Release** builds the site and PDF, creates the tag and the GitHub release, then republishes the site so it shows the new version.

| Since the last release | Version |
|---|---|
| A doctrine item (Parts 1, 2, 3.1–3.2) added, removed or its `version` bumped | major |
| Any other item added, removed or its `version` bumped | minor |
| Wording only | patch |

Before 1.0.0 each row moves down one step. You can choose a higher bump but never a lower one. Nobody types a version number, and CI rejects changelog headings that are malformed (`V1.2`, `v1.02.0`) or skip a version. The latest final PDF is always at `releases/latest/download/imt-doctrine.pdf`.

## First-time setup

1. Create a GitHub App for releases (no webhook; *Contents* and *Pull requests* read and write) and install it on this repository. From its settings page, run `gh variable set RELEASE_APP_ID --body <app-id>`, `gh variable set RELEASE_APP_CLIENT_ID --body <client-id>` and `gh secret set RELEASE_APP_KEY < key.pem`.
2. Push `main`, then run `tools/setup-repo.sh` (needs `gh` with admin rights; safe to run again). It turns on auto-merge and Discussions, makes the Actions token read-only, adds the `preview` label and the rulesets (only admins and the release app may change `v*` tags), turns on immutable releases and enables Pages from the `gh-pages` branch.
3. Publish the release waiting in the changelog: **Actions → Release → Run workflow**. After that, use Prepare release.

While the repository is private on GitHub Free, rulesets and Pages are unavailable. CI still runs, and each run's built site is downloadable as the `site` artifact. Both work once the repository is public (or on GitHub Pro).

While you're the only maintainer, run `tools/setup-repo.sh --solo`: pull requests then need passing checks but no approval. Run it again without `--solo` once reviewers join.

When the repository moves to an organisation, replace `@schmidtnz` in `CODEOWNERS` with the review group's team.

### Read the Docs (trial)

`.readthedocs.yaml` builds the same site on Read the Docs, alongside GitHub Pages. Sign in at <https://app.readthedocs.org> with GitHub and import this repository. It then builds `main` as "latest", HTML and PDF for each tag you activate under *Versions*, and an HTML-only preview for each pull request. The GitHub workflows still publish the site, PDF previews and releases.

## Licence

| Material | Licence |
|---|---|
| Code and configuration (`tools/`, `tests/`, `docs/_ext/`, `docs/_static/`, `docs/conf.py`, `.github/`, `.readthedocs.yaml`) | [MIT](LICENSE) |
| Doctrine content (everything else under `docs/`) | [CC BY 4.0](LICENSE-docs), pending confirmation by LandSAR |

The doctrine text is condensed from LandSAR's draft v0.1 and remains LandSAR's copyright. Until LandSAR confirms CC BY 4.0, the content is all rights reserved and shared for review only. Only doctrine published by LandSAR is authoritative; adapted copies must not present themselves as official. Third-party figures and forms are not covered by CC BY 4.0. See [NOTICE](NOTICE) for details.
