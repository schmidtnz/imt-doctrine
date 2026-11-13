---
id: CON-08
type: concept
title: Maths in SAR
version: 1
derives_from:
  PRN-08: 1
  PRN-11: 1
owner: doctrine-group
last_reviewed: 2026-10-01
---

# CON-08 Maths in SAR

Numbers run through land SAR: search area and travel distance, search urgency scores, lost person behaviour statistics, scenario weighting and probability of area. People interpret probability *words* very differently; numbers remove that ambiguity, even when the judgement behind them is subjective.

{term}`POD` is often reported as High, Medium or Low. Words alone can't be used to recalculate {term}`POA` after a segment is searched, which is central to progressive search management. The doctrine therefore binds each word to a number. A simple prompt: "If there were 10 people in your area, how many would you have seen?" Eight means 80 %.

```{include} ../../_snippets/pod-scale.md
```

Recalculating probability is covered in {doc}`con-17-search-theory`.

*Condensed from draft v0.1, Part 3.1 §8.*
