# Golden datasets you can run Policy Atlas against — a catalogue

**Question this answers:** *what existing labelled benchmarks exist that I can judge our retrieval
tool against* (recall + ranking relevance), given we search academic + policy literature and care
about the policy domain.

**Companion note:** `golden_datasets_research.md` answers the *other* question — how to build/trust
your own gold set when none fits. Read that one once you land in Tier A/B below ("borrow the topics,
build the judgments").

> **Revision (2026-06-25):** an earlier version of this catalogue used "the gold documents must be
> retrievable from our corpus" as a hard filter. That was wrong and has been removed — see the next
> section. The tiers below are re-ranked accordingly: datasets with a **curated relevant set + clean
> identifiers** now lead, even if their documents don't all live in OpenAlex/S2/Overton.

---

## Does a gold document have to be in your corpus? No — and that changes the ranking

This is the key correction, written out from first principles because it drives everything below.

**Recall asks one question: *of all the documents that should have been found, how many did we
find?*** The "should have been found" list — the denominator — comes from the golden dataset: a
human expert decided those documents are relevant. **Whether your tool *could* reach a given one is
not part of that question.** If a relevant document exists and your tool didn't return it, that's a
miss — and *why* it was missed doesn't change the arithmetic.

There are two reasons your tool can miss a relevant document, and both are real failures a user
would care about:

1. **It isn't in your corpus.** OpenAlex / S2 / Overton simply don't hold it, so no query could ever
   return it. → a **coverage** problem; the fix is adding sources (e.g. more grey literature).
2. **It's in your corpus but your search/ranking didn't surface it.** It was reachable; you just
   didn't bring it back. → a **retrieval** problem; the fix is a better retriever/ranker.

So a golden dataset whose relevant docs *aren't* all in your corpus is **more** useful, not less:
it's the only way to even see failure mode #1.

### The one real requirement: you must be able to *match* (identifiability ≠ findability)

To score recall you walk down the gold list and, for each document, ask "did the tool return this
one?" That needs a **shared label** between the gold list and the tool's output — a **DOI** (best) or
a **normalised title** (fallback). Call that *identifiability*.

It is a completely different requirement from *findability*:

| | Meaning | Required to score recall? |
|---|---|---|
| **Findability** | Could the tool dig this doc up from its sources? | ❌ No |
| **Identifiability** | If the tool returns a doc, can I tell it's the same as this gold doc? | ✅ Yes |

**The practical risk lives here:** if identifiers are messy — the gold set has no DOIs, or titles
are punctuated differently — you'll *fail to match documents you actually did find*, and report a
recall that's **too low**. The matching step is where silent errors hide, so spend effort on clean
DOI / normalised-title matching. This is a much weaker condition than "indexed in our corpus" — it's
just "the two ID spaces overlap enough to compare."

### Don't report one blended number — split the two failure modes

If you only report end-to-end recall, *"we found 60%"* is ambiguous: is the **corpus** missing the
evidence, or is the **ranker** weak? They have opposite fixes, so separate them:

```
gold relevant set  R   (the expert-curated denominator)
  │
  ├─ how many of R even exist in your corpus?
  │     → COVERAGE              = |R ∩ corpus| / |R|
  │
  └─ of the ones that DO exist, how many did the tool surface?
        → RETRIEVAL RECALL      = |returned ∩ R ∩ corpus| / |R ∩ corpus|

end-to-end PRODUCT RECALL ≈ COVERAGE × RETRIEVAL RECALL = |returned ∩ R| / |R|
```

In words: **coverage** = "what fraction of the relevant evidence is even reachable by us." **Retrieval
recall** = "of the reachable evidence, what fraction we actually showed the user." **Product recall** =
"of *all* the relevant evidence, what fraction reached the user" — coverage and retrieval multiplied.

**Worked example — one policy question with 40 expert-relevant studies:**

- 30 of the 40 exist in OpenAlex/S2 → **coverage = 30 / 40 = 75%**
- of those 30, the tool surfaced 24 → **retrieval recall = 24 / 30 = 80%**
- the user therefore saw 24 of 40 → **product recall = 24 / 40 = 60%**

Now "60%" is *actionable*: the corpus is the bigger bottleneck — it loses a quarter of the evidence
before retrieval even starts — so the highest-leverage fix is **adding sources**, not tuning the
ranker. Reporting a bare "60%" would have hidden that entirely. (This is exactly how systematic
reviewers benchmark a *database's* coverage against a known reference set — your instinct matches an
established evidence-synthesis practice.)

**What this means for the catalogue:** the bar is no longer "is it in our corpus." The bar is now
**(a) a curated/complete relevant set** and **(b) clean identifiers (DOIs/titles) so you can match**.
Domain fit (policy/social-science) is the tie-breaker. On that bar, the policy-domain datasets rise
to the top.

---

## Tier A — Policy / social-science domain, curated denominator (highest fit)

Best domain match *and* they clear the new bar (curated relevant set + identifiable docs). Corpus
membership is now just the coverage number you report, not a gate.

| Dataset | Domain | Relevant set & identifiers | What to do with it |
|---|---|---|---|
| **Campbell / 3ie / EPPI systematic reviews** (reconstructed — "unzip" the reviews) | **Exactly yours** — crime, education, social welfare, international development policy | each review = a policy question + an **expert-vetted included-studies list**, usually with **DOIs** → matchable | **The highest-fidelity policy gold data that exists.** Take 15–30 reviews in your priority areas; the included studies are R; run each review's question as a query; report coverage + retrieval recall + product recall. DIY effort, but it's the only data that is simultaneously policy-domain, expert-judged, and cleanly identifiable. Hands straight to the companion note for stratification/judging. |
| **CODEC** (Glasgow, SIGIR 2022) | **Social science — history, economics, politics** | 42 complex *essay-style* research topics; expert judgments on 17,509 docs/entities (~417/topic); TREC-style pooling; ships 387 query reformulations | Now usable two ways: (a) reuse the **42 expert topics as queries** and re-pool over OpenAlex, judging with your frozen judge; or (b) score over CODEC's own web corpus and read it as a coverage-included recall number. The complex-topic shape mirrors your PICO-folded `query_text`. |

**Recommendation for Tier A:** Treat the **Campbell/3ie unzip** as the real prize and start scoping
it (which review areas, DOI-extraction, sample size). Use **CODEC**'s 42 topics as a faster,
ready-made source of policy-flavoured complex queries while the bespoke set is built.

---

## Tier B — Systematic-review collections with *complete* denominators (true recall, near-policy)

These match your **high-recall evidence-review** objective and give what `recall@k_est` only
estimates: a (near-)**complete** relevant set per topic, so you can report a *true* recall number,
not an inflated estimate. Mostly biomedical — but **SYNERGY is multidisciplinary and includes social
science**, and all have clean identifiers.

| Dataset | Domain | Structure & identifiers | Verdict |
|---|---|---|---|
| **SYNERGY** (ASReview) | **Multidisciplinary incl. social science** | 26 fully-labelled reviews; 169,288 works; only **1.67% included** → per-review complete R + large negative pool; works carry **titles/abstracts/refs/DOIs** | **Best "true-recall + near-policy" option.** Filter to social-science reviews, map included studies to OpenAlex/S2, run each review topic as a query. The one place you can report *actual* recall (complete denominator) in a near-policy domain. |
| **CLEF eHealth TAR 2017/18/19** | Biomedical systematic reviews | 31 Cochrane reviews; complete relevance judgments; PMIDs (→ mostly DOI-mappable) | The canonical high-recall IR benchmark (`github.com/CLEF-TAR`). Biomedical, but the *evaluation design* — recall-at-effort with a real denominator — is the standard to emulate when you present numbers. |
| **Cohen 2006 drug-review set** | Biomedical | 15 reviews, complete labels, PMIDs | Small classic TAR set; handy for quick recall-curve sanity checks. |

**Recommendation for Tier B:** Pilot **SYNERGY** (social-science subset) for your first *true-recall*
measurement; use **CLEF-TAR** as the methodological reference for reporting recall-at-effort.

---

## Tier C — Instrument-validation benchmarks (runnable today, CS/biomed domain)

Wrong domain for policy claims, but they match your task shape and live on your corpus, so they
**validate the machinery** and give external comparison points. Run these *first* in calendar terms
even though they rank below A/B on domain fit — they're how you prove the harness itself is correct.

| Dataset | Queries | Identifiers | Why run it |
|---|---|---|---|
| **PaperFindingBench** (ASTA-bench) | 333 (48 navigational + 43 metadata + 242 semantic) | S2 CorpusIDs — **identical to your `paper_id`** | **Run first.** Your `metrics.py`/`eval.py` were ported *from this benchmark*, so scoring against it is ≈zero adapter code and regression-tests your whole instrument against Allen AI's own Paper Finder. Calibration target, not a policy test. |
| **LitSearch** (Princeton, EMNLP 2024) | 597 realistic literature-search questions (ML/NLP) | S2ORC IDs / DOIs | Independent, public, realistic-query benchmark on your corpus. Good for recall@k + ranking metrics. |
| **LitQA2** (FutureHouse, LAB-Bench) | biomedical literature questions | gold corpus IDs; recall@30 | Already wired into the ASTA task code you forked (`paper_finder_litqa2`). Cheap add. |
| **DORIS-MAE** (2023) | 100 complex multi-aspect scientific queries (→ ~4,000 sub-queries) | arXiv-derived | Borrow the **complex-query construction method** — closest structural match to a policy research question — even if you don't score on its corpus. |
| **CSFCube** (2020) | paper + facet as query | S2 papers, graded relevance | Query-by-example, not free-text search — a narrow ranking-quality probe, weaker task fit. |

---

## Tier D — Reference only (corpus *and* task mismatch)

Useful as methodology reading or corpus sources; not scoreboards for your retriever.

- **POLIS-Bench** (2025) — governmental policy clause retrieval, bilingual/Chinese-leaning gov docs. Methodology reference for policy-clause retrieval + LLM-judged policy eval.
- **Climate Policy Radar** — 6,000+ national laws/policies/UNFCCC submissions. A ready *policy-document corpus* (Overton-adjacent), not a query→relevance benchmark — a candidate testbed if you build judgments over it.
- **TREC Legal Track (2006–11)** — e-discovery high-recall tasks. The origin of "certify recall without a complete gold set" (ties to QBCB/Webber in the companion note).
- **Sci2Pol** (2025) — science→policy *brief generation*; out of scope for retrieval but relevant policy-NLP prior art.

---

## Bottom line / recommended sequence

1. **Prove the instrument (week 1):** run the harness against **PaperFindingBench** — ≈zero adapter
   cost, it *is* your metrics' source, and it gives an external comparison vs ASTA Paper Finder.
   Add **LitSearch + LitQA2** for breadth on your real S2 corpus.
2. **Get a true-recall number near your domain:** pilot **SYNERGY** (social-science subset, complete
   denominator, OpenAlex-mappable) — report coverage / retrieval recall / product recall separately.
3. **Get policy-domain signal fast:** reuse **CODEC**'s 42 social-science topics over your corpus.
4. **Build the thing that actually matters:** reconstruct ~15–30 gold sets from **Campbell / 3ie /
   EPPI** reviews in your priority policy areas — the only data that is policy-domain, expert-judged,
   and cleanly identifiable. Then the companion note (`golden_datasets_research.md`) tells you how to
   stratify it, anchor the LLM judge to it, and report recall with honest confidence intervals.

**The reframed summary:** dropping the corpus-membership gate changes the conclusion. You are *not*
stuck with CS/biomed proxies — **any expert-curated relevant set with clean DOIs/titles is fair
game**, and documents your corpus can't reach become a *coverage finding* rather than a reason to
discard the dataset. So the policy-domain options (Campbell/3ie, CODEC) move to the front; the
academic benchmarks (PaperFindingBench/LitSearch) stay only as instrument-validation; and the single
highest-value build is unzipping real policy systematic reviews. Always report the
coverage / retrieval / product split so a "60%" tells you whether to fix the **index** or the
**retriever**.

---

## Sources

- LitSearch (EMNLP 2024) — https://github.com/princeton-nlp/LitSearch · https://arxiv.org/abs/2407.18940 · https://aclanthology.org/2024.emnlp-main.840/
- DORIS-MAE (2023) — https://arxiv.org/abs/2310.04678
- SciRepEval (EMNLP 2023, incl. CSFCube) — https://aclanthology.org/2023.emnlp-main.338.pdf
- CODEC (SIGIR 2022) — https://github.com/grill-lab/CODEC · https://arxiv.org/pdf/2205.04546 · https://dl.acm.org/doi/10.1145/3477495.3531712
- POLIS-Bench (2025) — https://arxiv.org/abs/2511.04705
- Sci2Pol (2025) — https://arxiv.org/html/2509.21493
- Climate Policy Radar — referenced via https://arxiv.org/pdf/2410.23902
- SYNERGY (ASReview) — https://github.com/asreview/synergy-dataset · https://asreview.nl/data-scientists/
- CLEF eHealth TAR 2019 — https://github.com/CLEF-TAR · https://ceur-ws.org/Vol-2380/paper_250.pdf
- Campbell Collaboration EGM guidance — https://onlinelibrary.wiley.com/doi/10.1002/cl2.1125 ; 3ie evidence gap maps — https://www.3ieimpact.org/evidence-hub/evidence-gap-maps
- PaperFindingBench / LitQA2 — ASTA-bench (`astabench/evals/paper_finder`), already vendored in your tree
