# Citation snowballing — an explainer

How the retrieval experiment (`backend/testing/r_and_d/search_experiments/snowball.py`,
spec `docs/specs/spec_retrieval_experiment_openalex.md` §4.3 Step 3) expands a relevant seed
set by walking the citation graph, and how candidates are scored and promoted. A faithful port
of Paper Finder's `score_snowball_candidate`
(`asta-paper-finder/agents/.../snowball/snowball_agent.py:319-365`).

---

## 1. Why snowball at all?

The v2 baseline is **open-loop**: one query → one result page → done. But the literature is a
*graph*, not a list. Once the judge has confirmed a few genuinely relevant papers (the
"seeds"), their bibliographies and the papers citing them are unusually dense with more
relevant work — far denser than a fresh keyword query. Snowballing is the **closed-loop**
move: feed confirmed relevance back into retrieval by following citations out from the seeds.

> ★ Key points
> - **Seeds = papers judged ≥ 2** (Highly/Perfect). Relevance is judge-gated, so snowball only
>   ever expands from confirmed-good anchors (spec §4.3 Step 3).
> - It runs as the **expansion** step of each search iteration, *between* the two adaptive
>   judging passes — newly promoted candidates are themselves judged in pass 2.
> - It is one of several **origins** competing for judging budget in the bandit
>   (`forward-snowball`, `backward-snowball` are arms — see the BTS explainer).

---

## 2. The citation graph and "edges"

Papers are **nodes**; a citation is a directed **edge**. Snowballing walks one hop out from
each seed, in two directions:

| Direction | Walk | Yields | Tends to surface |
| --- | --- | --- | --- |
| **backward** | the seed's **references** (its bibliography) | papers the seed builds on | older, foundational work |
| **forward** | the papers that **cite** the seed | papers building on the seed | newer, follow-on work |

The thing that makes scoring interesting: **one candidate can be reached from several seeds**,
i.e. sit at the end of several edges. That co-citation is a strong relevance signal:

```
S1 (rel 1.00) ─┐
S2 (rel 0.67) ─┼─→  X      X has 3 edges (n_edges = 3); reached from 3 relevant seeds
S3 (rel 1.00) ─┘

S2 (rel 0.67) ───→  Y      Y has 1 edge
```

X is co-cited by three relevant seeds; Y by one. A faithful score must reward X for that — which
is precisely why we score over **edges**, not over a single merged `Candidate` (a plain
`max(seed_relevance)` would collapse X's three edges into one and discard the signal).

### `SnowballEdge` — the unit we score over

```python
@dataclass
class SnowballEdge:
    candidate: Candidate
    seed_relevance: float        # seed.level / 3, in [0,1]
    is_influential: bool = False # whether THIS citation is influential (S2 forward signal)
```

`build_edges` makes one seed's hop into edges, carrying the seed's relevance to each candidate
and **capturing `is_influential` now** — before any later dedupe/merge unions the flag — because
PF treats influence as a property of the individual citation:

```python
def build_edges(seed: Candidate, reached: Iterable[Candidate]) -> list[SnowballEdge]:
    seed_rel = (seed.level or 0) / 3.0
    return [SnowballEdge(candidate=c, seed_relevance=seed_rel, is_influential=c.is_influential)
            for c in reached]
```

---

## 3. The scoring formula (PF, ported verbatim)

For one candidate, sum over its edges:

```
score = Σ_edges [ seed_relevance_bias · seed_relevance
                  + influential_bias  · is_influential        (forward + Arm C only)
                  + count_bias        · candidate_count ]
```

The coefficients are frozen in `config.SnowballWeights`; the direction-specific pieces:

| Term | forward | backward | Source |
| --- | --- | --- | --- |
| `seed_relevance_bias` | 1.0 | 1.0 | confirmed seeds pull hardest |
| `influential_bias` | 0.1 (Arm C) / 0 (Arm B) | 0 | S2 influence signal; OpenAlex has none (§4.3 diff #2) |
| `count_bias` | −0.005 | −0.0005 | mild penalty on already-heavily-connected papers |
| `candidate_count` | `max(reference_count, n_edges)` | `max(cited_by_count, n_edges)` | PF uses *different* count fields per direction |

In code (`score_snowball_candidate`):

```python
count = _candidate_count(cand, direction, len(edges))   # forward: reference_count; backward: cited_by_count
if direction == "forward":
    count_bias = w.forward_citation_count_bias            # -0.005
    influential_bias = w.influential_bias if caps.has_influential else 0.0  # 0.1 (Arm C) / 0 (Arm B)
else:
    count_bias = w.backward_citation_count_bias           # -0.0005
    influential_bias = 0.0                                # backward carries no influence term

score = 0.0
for e in edges:   # PF sums every term per edge — incl. the constant count penalty (-> × n_edges)
    score += (w.seed_relevance_bias * e.seed_relevance
              + influential_bias * int(e.is_influential)
              + count_bias * count)
```

### Faithfulness notes (what is exact, and the only context-forced changes)

1. **The count penalty is inside the per-edge loop**, so it is added once per edge → effectively
   `× n_edges`. Odd, but it is PF's actual behaviour, so we keep it.
2. **Forward penalises by reference count, backward by citation count** (PF uses different
   DataFrame columns). Our `Candidate` gained a `reference_count` field to model this; the spec
   had simplified both to citation count, so this is *more* faithful than the spec shorthand.
3. **`influential_bias` is forward-only and Arm-C-only.** `caps.has_influential` gates it off
   for Arm B — OpenAlex exposes no influential-citation signal (source-forced, spec §4.3 diff #2).
4. **`num_contexts_bias` and `seed_citation_count_bias` are dropped.** Both are `0` in PF's
   defaults and the spec, so this is a ×0 term — exact, not a simplification.

---

## 4. Grouping and promotion

`group_edges_by_candidate` does the co-citation grouping (all edges into the same `paper_id`),
and `promote_snowball` scores each group and keeps the top-k (PF promotes ~200 per direction,
`config.budgets.snowball_top_k`):

```python
def promote_snowball(edges, direction, caps, top_k=None):
    top_k = top_k or CONFIG.budgets.snowball_top_k
    grouped = group_edges_by_candidate(edges)
    scored = [(score_snowball_candidate(cand_edges, direction, caps), cand_edges[0].candidate)
              for cand_edges in grouped.values()]
    scored.sort(key=lambda pair: pair[0], reverse=True)   # stable: ties keep discovery order
    promoted = []
    for score, cand in scored[:top_k]:
        cand.seed_relevance = score    # recorded for inspection; unused by ranking downstream
        promoted.append(cand)
    return promoted
```

The promoted candidates re-enter the pool and are judged in the iteration's **second adaptive
pass** (spec §4.3 Step 4) — so snowball doesn't add to the ranked output directly; it adds
*candidates to be judged*, and only judged-relevant ones survive to ranking (§4.3 Step 5).

---

## 5. Worked example

Forward snowball, **Arm C** (`has_influential=True`). Candidate **X** reached from three seeds;
only S1's citation is flagged influential; `X.reference_count = 40` (so `candidate_count =
max(40, 3) = 40`):

| edge | `seed_relevance` | `is_influential` | contribution = `1.0·rel + 0.1·infl − 0.005·40` |
| --- | --- | --- | --- |
| S1→X | 1.00 | yes | `1.00 + 0.10 − 0.20 = 0.90` |
| S2→X | 0.67 | no | `0.67 + 0.00 − 0.20 = 0.47` |
| S3→X | 1.00 | no | `1.00 + 0.00 − 0.20 = 0.80` |
| | | **score(X)** | **2.17** |

Candidate **Y** reached from one seed (S2, rel 0.67), not influential, `reference_count = 10`
(`candidate_count = max(10, 1) = 10`):

```
score(Y) = 1.0·0.67 + 0.1·0 − 0.005·10 = 0.62
```

**X (2.17) ≫ Y (0.62)** — the co-citation by three relevant seeds is what separates them, exactly
as intended. On **Arm B** the same X loses only its influence term: `2.67 − 0.6 = 2.07` (the
`0.1` on S1's edge disappears), so the ranking among OpenAlex candidates is essentially preserved
while honouring the source-forced difference.

---

## 6. Where it sits / provenance

- **Pipeline position:** spec §4.3 Step 3 (expansion), between adaptive judging pass 1 (Step 2)
  and pass 2 (Step 4). Seeds = judged ≥ 2; promoted candidates are judged next.
- **Arm B vs C:** mechanism-identical except `influential_bias` (gated by `caps.has_influential`)
  and the source of citations (OpenAlex `referenced_works` / `cites:` vs S2 `/references` /
  `/citations`). The shared `broad_search` loop calls the same `snowball.py` for both.
- **Provenance:** faithful port of PF `score_snowball_candidate`
  (`snowball_agent.py:319-365`); constants in `config.SnowballWeights`. We reimplement over our
  own `Candidate`/`SnowballEdge` rather than PF's `DocumentCollection`, dropping only its ×0
  default terms.

> ★ Bottom line
> Snowballing turns confirmed relevance into more candidates by walking the citation graph, and
> the score rewards **co-citation by relevant seeds** (the per-edge sum) while mildly penalising
> already-saturated papers. It is the graph-shaped half of the closed loop — the bandit
> (BTS explainer) is the budget-shaped half.
