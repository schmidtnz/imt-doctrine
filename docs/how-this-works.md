# How this doctrine is maintained

## Two review tiers

| Tier | Folders | To merge a change |
|---|---|---|
| Doctrine | Parts 1, 2, 3.1, 3.2, glossary, shared snippets | Approval from a doctrine owner (sector review group) |
| Guidance | 3.3–3.6, forms | One approval from any reviewer |

Doctrine changes slowly and needs agreement; guidance and forms change often and need light review. The split is set in `.github/CODEOWNERS`.

## Items and derivation

Principles, concepts, guidelines, processes and forms are **items**. Each item page starts with a short block of metadata:

```yaml
---
id: GDL-02
type: guideline
title: Recording POD at the team debrief
derives_from:
  CON-02: 1        # parent ID: parent version this was written against
owner: doctrine-group
last_reviewed: 2026-10-01
---
```

Allowed links run down the hierarchy: principle → concept → guideline → process → form. A guideline can't derive straight from a principle.

When an item's meaning changes, its author bumps `version`. Every child written against the old version is then listed as **stale** on the {doc}`status/traceability` page until someone checks it and updates its `derives_from` number. The tooling confirms that someone *looked*; it can't judge whether the child is still right.

## Checks on every change

| Check | Result |
|---|---|
| Parent ID doesn't exist, or wrong parent type | Fails |
| Child claims a newer parent version than exists | Fails |
| Item needs children and has none | Warning |
| Child written against an older parent version | Listed as stale |
| Parent text changed but version not bumped | Warning |
| `last_reviewed` older than the review interval | Listed as overdue |

## Say it once

- Repeated text, such as the {term}`POD` scale, lives in one snippet file and is included wherever it's needed.
- Acronyms are defined once in the {doc}`glossary`.
- The organisation name comes from one setting, so it reads "{{ org }}" everywhere.

## Releases

Each tagged release (for example `v1.2`) publishes the site and a PDF. Operational reviews cite the version number shown at the top of every page.
