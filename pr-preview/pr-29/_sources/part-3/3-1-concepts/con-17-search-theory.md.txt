---
id: CON-17
type: concept
title: "Search theory: POA × POD = POS"
version: 1
derives_from:
  PRN-08: 1
  PRN-11: 1
owner: doctrine-group
last_reviewed: 2026-10-01
index: [closed search area, segments]
---

# CON-17 Search theory: POA × POD = POS

Search planning comes down to two things: finding the right place to search, and applying resources that can detect what you are looking for, at the right time.

```{math}
POS = POA \times POD
```

- {term}`POA`: the likelihood the subject is in this region or segment.
- {term}`POD`: the likelihood this resource would find the subject if they were there.
- {term}`POS`: the overall likelihood of success.

## Closed search system

New Zealand uses a **closed search area**: the IMT defines a bounded area and assumes the subject is inside it. The rest of the world is not forgotten; it is covered by investigation and public appeals, not by searching.

## Search area, regions and segments

In the initial response the search area is set by LPB statistical rings, theoretical travel distance and any early scenarios. In extended search planning it is refined into a shape that follows terrain and evidence; the rings remain for reference only.

The refined area is divided into about 6–10 **regions** along clear terrain features: scenario-based regions (usually higher POA) and geographical regions. High-POA regions are divided into **segments**, each sized for a 4–6 hour task.

## Scenarios and weighting

A scenario is a story that runs from the planning point to a specific piece of terrain. "Lost somewhere in the area" is not useful. Present all the evidence to the IMT first, then test each scenario: does it fit the facts, is it realistic, is it consistent with LPB and the profile, is it achievable in this terrain, and what evidence contradicts it?

Weight scenarios with the {doc}`scenario weighting sheet </forms/frm-02-scenario-weighting>` or, where evidence is complex, with analysis of competing hypotheses ({term}`ACH`), which looks for the scenario *least contradicted* by the evidence. The two are complementary.

## Recalculating after a search

When a segment is searched and the subject isn't found, its POA drops:

```{math}
POA_{new} = POA_{old} \times (1 - POD)
```

For example, a segment weighted 14 searched at 80 % POD drops to 14 × 0.2 = 2.8. A second search with a different resource reduces it further. The IMT, not the field team, owns the final POD: it checks the debrief against GPS tracks, photos and conditions before using it, because an inflated POD moves the search away from a poorly searched area.

```{include} ../../_snippets/pod-scale.md
```

:::{note}
How ACH results translate into segment weights, and tools for more objective POD, are open questions in the draft.
:::

*Condensed from draft v0.1, Part 3.1 §17.*
