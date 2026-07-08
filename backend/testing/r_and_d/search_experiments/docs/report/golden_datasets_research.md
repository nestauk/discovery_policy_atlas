# Golden datasets for the search experiment: what we can measure, and how far to trust it

**Audience:** whoever owns the `search_experiments` harness and the companion judge spec.
**Status:** research note (2026-06-25). Feeds the Phase 10 `findings.md` and the
`spec_relevance_judge_experiment.md` companion. Not a spec change.

**Scope.** This note answers two questions the harness raises but cannot answer from inside
itself: (1) *can* we legitimately measure recall and ranking relevance with a pooled-normalizer
+ frozen-LLM-judge design, and (2) given the policy domain and a small annotation budget, what
is the highest-leverage way to build or augment a golden dataset. It draws on the established IR
test-collection literature (TREC pooling, sample-based estimation, capture–recapture, recall
confidence intervals, TAR stopping rules) and the recent LLM-as-judge literature, and maps each
result onto our specific config (`recall@k_est`, inflation factor `max(2, 2/ln(count))` capped at
10, Perfect-only numerator, the §4.6 normalizer-only lenient runs, and the gpt-5.x-judges-gpt-5.x
coupling).

**How to read the confidence tags.** Findings marked **[verified]** passed a 3-vote adversarial
check against primary sources (SIGIR/CIKM/TOIS/KAIS/NIST). Findings marked **[abstract]** come
from a paper's abstract only (full-text not parsed). Findings marked **[refuted]** are things the
research *killed* — listed so we don't accidentally rely on them.

---

## TL;DR for the harness

1. **Our design is sound as a *relative* instrument and unsound as an *absolute* one — and that
   is exactly what the spec already claims.** The IR literature is unambiguous: pooled judgments
   systematically under-credit systems that did not contribute to the pool, so `recall@k_est`
   ranks Arm A vs B vs C defensibly but cannot certify "we find X% of the relevant literature."
   Keep the headline framed as a ladder, not a coverage certificate. [verified]

2. **The pooling bias is *conservative* only because — and as long as — the judge is independent
   of the systems.** That guarantee (unjudged-relevant counted as non-relevant → scores only
   *depressed*, never inflated → improvement claims stay valid) is the load-bearing assumption
   behind every "relative comparison is fine" argument. **Our gpt-5.x-judges-gpt-5.x-retrieval
   coupling is precisely the case that can break it**, because self-preference can make the bias
   *non-uniform across arms* rather than uniformly conservative. This is the single most important
   risk to retire, and it is retireable with one ablation (judge with a different model family on a
   sample). [verified core; coupling-specific extension is theoretically motivated, not yet
   empirically quantified for our setup]

3. **The inflation-factor `k_est` is a heuristic where the field has principled estimators with
   error bars.** If we ever need a trustworthy denominator (not just a ranking), the rigorous
   replacements are statistical, not heuristic: sample-based unbiased estimators (infAP /
   Horvitz–Thompson) for *metrics*, and capture–recapture (Chao) or beta-binomial recall CIs for
   the *relevant-set size*. All three need a small amount of **randomly sampled** annotation that
   the current pool does not provide. [verified]

4. **The closest prior art to our problem is not CS paper-finding — it is systematic-review and
   legal e-discovery TAR**, which have spent fifteen years certifying high recall against an
   unknowable denominator. That is where to borrow from. [verified for the statistics; domain
   transfer to policy/PICO relevance is an additional unvalidated layer]

5. **Highest-leverage spend of a small annotation budget:** a stratified human-labelled sample
   that does triple duty — (a) calibrate the LLM judge against humans, (b) measure pool bias via
   leave-one-arm-out, (c) anchor a recall confidence interval. Whether one sample can serve all
   three depends on the sampling design (see §6); a uniform random sample is the most reusable
   starting point.

---

## 1. Test-collection construction and the limits of pooling

### 1.1 What pooling buys and what it costs

TREC-style pooling — judge the union of the top-*k* from each contributing run, treat everything
outside the pool as non-relevant — is the standard answer to "you cannot judge the whole corpus."
Our `search_experiments` pool (Arms A/B/C + the §4.6 normalizer-only lenient runs) *is* a depth-*k*
pool with a domain-specific contributor set. The literature tells us exactly what that costs.

> "Documents outside the depth-*k* pool are considered irrelevant... the underestimation of recall
> and the pooling bias generated when re-using these pooled collections to evaluate novel systems
> that retrieve relevant but unjudged documents are well-known problems."
> — Li & Kanoulas, *Active Sampling for Large-scale IR Evaluation*, CIKM 2017. **[verified]**

So the harness's "cannot certify absolute recall" caveat is not conservatism — it is the
established baseline finding. Two further results sharpen *how* it bites us:

- **Pool bias grows with collection size, not with the number of relevant docs**, and it favours
  relevant documents that contain the topic's title words, *squeezing out* relevant documents that
  don't — which structurally penalises semantic / concept-based retrieval.
  > "the assumption of unbiased judgments is violated when traditional pooling is used with a
  > constant pool size and increasing document set size... This phenomenon is wholly dependent on
  > the collection size and does not depend on the number of relevant documents for a given topic
  > ... pools ... exhibit a specific bias in favor of relevant documents that contain topic title
  > words ... these documents fill the pool, squeezing out other kinds of relevant documents."
  > — Buckley, Dimmick, Soboroff & Voorhees, *Bias and the Limits of Pooling for Large
  > Collections*, Information Retrieval 2007. **[verified]**

  **Direct relevance to us:** OpenAlex (Arms A/B) and S2 dense (Arm C) are exactly a lexical-vs-
  semantic contrast. If the pool is dominated by lexical/title-word hits, Arm C's dense leg — the
  thing the B→C step is supposed to measure — is the most likely to be *under-credited* by a
  relevant-but-unjudged document. The §4.6 "S2 lenient dense sweep" in the normalizer is, in effect,
  a home-grown mitigation for precisely this bias; the literature endorses the instinct.

- **The bias is worst in cross-type comparisons.** Yilmaz, Craswell, Mitra & Campos
  (*On the Reliability of Test Collections for Evaluating Systems of Different Types*, SIGIR 2020)
  measured a traditional-only depth-10 pool evaluating neural systems at Kendall's τ as low as
  **−0.12 (MRR)** and **0.68 (NDCG@10)**, vs **0.64–0.84** when the pool itself contained neural
  runs. Their verdict: *"traditional pools result in poor evaluation results for the neural
  systems. In fact, traditional pools seem to be worse than neural pools even for evaluating ...
  traditional systems that did not contribute to the pool!"* **[verified]**

  This is the formal warning against pooling from a narrow set of arm types. Our pool has three
  arms plus lenient sweeps, which is better than a single-type pool — but the A→B→C ladder is
  itself a "different system types" comparison, so this is the relevant failure mode, not an
  academic aside.

### 1.2 The conservativeness guarantee — and why coupling threatens it

The reason the field tolerates pool bias for *relative* comparisons is a specific guarantee:

> "the comparison problems on these unfair collections are conservative problems, in the sense
> that the score of a run affected by the bias in judgments will only be negatively affected
> (unjudged relevant documents will be counted as non-relevant)." — Buckley et al. 2007.
> **[verified]**

Improvement-over-baseline claims therefore survive pool bias: a genuinely better method might
*fail to show* a gain it deserves, but the bias won't *manufacture* a gain. **This is the entire
basis for trusting the A→B→C ladder.**

The critical caveat — flagged by the adversarial verifier and consistent with §2 of our spec — is
that **this guarantee assumes an independent pool/judge.** Classical pooling has humans judging
runs produced by unrelated systems. Our harness has a gpt-5.x judge scoring candidates surfaced
and ranked by gpt-5.x machinery. If the judge exhibits self-preference toward text the model
family finds familiar (see §3), the "unjudged-relevant → non-relevant" depression is no longer
*uniform across arms*: the arm whose retrieval/formulation is most stylistically aligned with the
judge could be *less* depressed than its rivals. That converts a conservative, ranking-preserving
bias into a potentially **rank-distorting** one. Nothing in the classical literature rules this in
or out for our setup — it is the open question that most deserves an in-harness ablation (§3, §6).

### 1.3 So how sound is "pooled normalizer + inflation factor" vs the alternatives?

| Property | Our `recall@k_est` (pool + inflation) | Sample-based estimators (infAP / HT) | Capture–recapture / recall CI |
|---|---|---|---|
| Certifies *relative* ranking of arms | ✅ (conservative, *if* judge independent) | ✅ | n/a (estimates a quantity, not a ranking) |
| Certifies *absolute* recall | ❌ (denominator is a heuristic guess) | ◑ (unbiased metric, still needs the relevant set) | ✅ with explicit CI |
| Reusable for a *future* arm not in the pool | ❌ (out-of-pool = non-relevant) | ✅ (judgments reusable without systematic error) | ◑ (depends on design) |
| Annotation design required | none beyond the pool | **uniform random sample** of the pool | **random sample** (incl. unretrieved segment) |
| Gives error bars | ❌ | ◑ (variance estimable) | ✅ (the whole point) |

The inflation factor is a reasonable *bounding* device — and the spec is honest that it caps
achievable recall (×2 → max 0.5) so "0.52" reads as "52% of an inflated estimate," not "missed
half." But it is a point heuristic with no error bar, and §2 below shows that point recall
estimates are specifically untrustworthy in our regime. The principled replacements all require
the one thing the pool lacks: **randomly sampled** judgments.

---

## 2. Estimating recall without an exhaustive gold set

This is the heart of the matter, and the field has three mature, mutually compatible answers — all
of which give *error bars*, which `k_est` does not.

### 2.1 Sample-based metric estimation (infAP / Horvitz–Thompson)

Inferred AP (infAP) equals AP when judgments are complete and is an **unbiased statistical
estimate** of AP when the judged set is a *uniform random sample* of the pool:

> three measures "equivalent to average precision when relevance judgments are complete and ...
> statistical estimates of average precision when relevance judgments are a random subset of
> complete judgments." — Yilmaz & Aslam, *Estimating average precision when judgments are
> incomplete*, KAIS 2008 (official TRECVID 2006 metric). **[verified]**

The **key condition is uniform random sampling** — which our normalizer-only lenient runs are
*not* (they are deliberately lenient/high-recall, i.e. a biased sample). So infAP/HT apply to a
*sampled-judgment design we would have to add*, not to the raw pool as it stands. Li & Kanoulas'
Horvitz–Thompson active sampling makes the reusability payoff explicit:

> "our approach is a sample-based approach [so] the estimated evaluation measures are, by
> construction, unbiased on average, and judgments can be used to evaluate new, novel systems
> without introducing any systematic error." — Li & Kanoulas, CIKM 2017. **[verified]**

That last property — *reusable for arms not yet built* — is exactly what a fixed pool cannot give
us, and it is worth a lot for a multi-phase experiment that will keep adding arms.

> ⚠️ **Wording precision (keep these directions straight in the report):** for a *novel/non-
> contributing* system, an incomplete pool **under**-estimates recall (its unique relevant docs are
> unjudged → counted as misses). For the *pooled systems themselves*, recall is **over**-estimated,
> because the denominator (count of known-relevant) is itself incomplete. Both are true; they
> describe different systems. [verified]

### 2.2 Capture–recapture for the relevant-set size (Chao)

The denominator we *guess* with the inflation factor can instead be *estimated*. Treat each
retrieval method as a "capture occasion": the total relevant set `|D+| = |L+|` (found) `+ |U+|`
(not yet found), and you can estimate `|U+|` from the overlap structure of what different methods
captured.

> "The set D+ consists of ... the set found by the user (L+) and the set ... [that] yet eluded the
> search process (U+) ... The user can stop the process once the estimate |D+| approaches |L+|."
> ... "We employ an ensemble of Active Learning methods that individually rank and propose
> documents ... maintain a registration list containing the identifiers of documents identified by
> each method." — Bron et al., *Using Chao's Estimator as a Stopping Criterion for TAR*, ACM TOIS
> 2024/25 (arXiv 2404.01176). **[verified]**

**This maps almost one-to-one onto our harness:** our arms and normalizer runs already *are* an
ensemble of methods with per-method "registration lists" (origin attribution is already a §4.7
metric). We could compute a Chao estimate of `|D+|` from arm-overlap and compare it against
`k_est` — a near-free sanity check on the inflation heuristic. **Caveats the source insists on:**
Chao's estimate is only a **lower bound** on relevant docs; it fluctuates wildly early (the authors
gate on `|L+| > 100` and use CI upper bounds, not point estimates); and ensemble members are not
truly independent capture sources, so the estimator has to tolerate dependence. With only ~26
queries and small per-query Perfect counts in sparse strata, expect the estimate to be noisy
exactly where we most want it.

### 2.3 Recall confidence intervals (Webber) — and why point estimates are dangerous for us

If we sample the retrieved and unretrieved segments and compute relevance prevalence in each, we
get a recall estimate. Webber's central warning is that the **bare point estimate is actively
misleading in the high-recall, low-prevalence regime we live in**:

> "Small samples may find no relevant documents in the unretrieved segment, leading to the
> misleading impression of perfect recall ... a perverse incentive to reduce sample size." The fix:
> "Our final approach derives beta-binomial posteriors on retrieved and unretrieved yield ... the
> half prior gives best results ... mean coverage at or near the nominal level, across several
> scenarios." — Webber, *Approximate Recall Confidence Intervals*, ACM TOIS 2013 (arXiv 1202.2880).
> **[verified]**

**Actionable rule for our report:** whenever we publish a recall number that is meant to be
absolute (not a relative ladder rung), report a **beta-binomial recall CI with half-priors
(hyperparameters = 0.5)**, not a point estimate. This is cheap, and it directly defuses the
"sparse stratum reads as suspiciously high/low recall" interpretation problem the spec already
worries about.

### 2.4 If recall ever becomes a stopping/selection criterion: beware sequential bias

We don't currently stop on recall, but the companion judge spec and any "lenient sweep until the
denominator stabilises" logic could drift into it. The warning:

> "the PET [Point Estimate Threshold] rule is statistically biased: the expected value of
> effectiveness at the stopping point typically falls short of the claimed effectiveness level ...
> conditioning stopping of a process on a random variable makes the stopping point itself a random
> variable." — Lewis, Yang & Frieder, *Certifying One-Phase TAR*, CIKM 2021 (arXiv 2108.12746).
> **[verified]**

The same paper gives the rigorous end-state if absolute recall certification ever becomes a hard
requirement — the **QBCB** rule, a distribution-free CI on recall from order statistics of a
positive (relevant) random sample:

> "with at least 1−α probability over draws of the random sample, the t-quantile b_t falls within
> the sample-based realization [d_i, d_j] ... we thus have 1−α confidence that stopping at d_j gives
> a recall of at least t." ... "we provide the first broadly applicable and statistically valid
> sample-based stopping rules for one-phase TAR." **[verified]**

---

## 3. The LLM-as-judge layer: agreement, and the coupling risk

Two distinct questions: *is the LLM judge any good?* and *is it dangerous that the judge shares a
model family with the retriever?*

### 3.1 LLM judges agree with humans well enough to rank systems

The strongest evidence is the Bing/Microsoft work behind UMBRELA:

> LLM relevance labels reach "accuracy as good as human labellers," show "similar capability to
> pick the hardest queries, best runs, and best groups," and "produce better labels than
> third-party workers, for a fraction of the cost." Caveat: "systematic changes to the prompts make
> a difference in accuracy, but so too do simple paraphrases."
> — Thomas, Spielman, Craswell & Mitra, *Large language models can accurately predict searcher
> preferences*, arXiv 2309.10621 (2024). **[abstract]**

Two takeaways for us: (1) the "pick the best run/group" finding is the *relevant* validity claim —
it says LLM judges preserve **system rankings**, which is exactly what the A→B→C ladder needs; (2)
the prompt-sensitivity warning ("even paraphrases matter") is why our **frozen-judge** discipline
(one prompt, one model, cached, applied identically to every arm) is methodologically correct and
should be defended as a feature, not an implementation detail.

### 3.2 Self-preference bias is real and is the mechanism behind our coupling worry

> "GPT-4 exhibits a significant degree of self-preference bias." The mechanism is **perplexity
> familiarity**: "LLMs assign significantly higher evaluations to outputs with lower perplexity than
> human evaluators, regardless of whether the outputs were self-generated ... the self-preference
> bias exists because LLMs prefer texts more familiar to them."
> — Wataoka, Takahashi & Ri, *Self-Preference Bias in LLM-as-a-Judge*, arXiv 2410.21819 (2024).
> **[abstract]**

This is the precise threat to §1.2's conservativeness guarantee. The bias is *not* strictly
"the model favours its own outputs" — it is "the model favours text that scores low-perplexity
under its distribution." In our harness the judge doesn't score model-*generated* text; it scores
real papers. So the naive circularity ("it grades its own essays") doesn't apply directly. **But**
the *formulation and reranking* are model-driven: which candidates reach the pool, and in what
order, is shaped by gpt-5.x. If the judge systematically rates the kinds of papers our gpt-5.x
formulation surfaces as more relevant — because they're the familiar, low-perplexity matches to a
gpt-5.x-written query — the across-arm bias becomes non-uniform. That is a plausible, named,
literature-grounded mechanism, **not** a confirmed effect size for our setup.

### 3.3 Mitigations (in rough order of leverage)

1. **Cross-family judge ablation.** Re-judge a stratified sample of the pool with a judge from a
   *different* model family (e.g. a Claude- or Gemini-class judge) and recompute the A→B→C ladder.
   If the ranking and the per-arm recall gaps hold, the coupling risk is empirically retired for
   this experiment. If they move, you have quantified it. This is the single highest-value
   follow-up and it is cheap (re-judge only, no re-retrieval — the pool and evidence snippets are
   cached).
2. **Human anchor.** Validate the frozen judge against a stratified human-labelled sample (§6);
   report agreement (Cohen's κ, and crucially *system-ranking* agreement à la Thomas et al.).
3. **Keep the judge frozen and content-only** (already done): no PICO/study-design logic in the
   judge, one cached prompt. This bounds prompt-sensitivity variance and keeps the instrument
   identical across arms.
4. **Evidence-grounded judging** (already done): judging from extracted evidence snippets rather
   than letting the judge free-associate reduces the surface for stylistic self-preference.

> **Evidence gap (be honest in the report):** the deep-research pass confirmed the *statistical*
> core 22/22 but did **not** surface verified, quantified effect sizes for LLM-judge self-preference
> *in an IR retrieval-evaluation setting specifically*. Treat §3.2 as a well-motivated risk to test,
> not a measured quantity. The cross-family ablation is how we turn it into a number.

---

## 4. Ranking-relevance metrics: why recall + nDCG (not precision) is the right call

Our choice — headline `recall@k_est`, balanced by lower-bound-corrected nDCG, combined via
harmonic mean (adjusted F1) — matches ASTA and is well-justified:

- **Graded (0–3) over binary.** Policy relevance is genuinely graded (a paper can be on-topic but
  wrong population/geography). Graded relevance is what nDCG is built for, and the 0–3 bucketing
  via weighted criteria (`metrics.relevance_criteria_score` → `bucket_0_to_3`) is the standard ASTA
  construction. Binary relevance throws away the Highly/Somewhat distinction that matters when you
  later stratify by evidence type.
- **nDCG rather than precision as the ranking balance.** ASTA's own rationale (PaperFindingBench
  README): *"We balance recall@k not by precision, but by nDCG, as it provides a more relevant
  signal (favoring ranking relevant documents over irrelevant ones). The combination of nDCG and
  recall@estimated makes precision mostly redundant."* For a coverage-objective tool — find the
  evidence, ranked — this is correct: precision penalises returning a long list, but a policy
  evidence review *wants* the long list as long as the good stuff is ranked up. nDCG rewards exactly
  that.
- **`recall@R` is an established metric, not an ASTA invention.** Computing recall at *k = estimated
  relevant-set size* is the standard `recall@R` / R-precision family; our only twist is that R is
  *estimated* (and inflated) rather than known. That twist is the §1–§2 story, not a metrics
  problem.

One caution surfaced and **refuted** — do not "fix" incompleteness by switching the headline to
**bpref**. The claims that bpref is invariant to unjudged documents and stays τ > 0.9 far longer
than MAP were *killed* in verification (0-3 and 1-2). Use the sample-based estimators of §2, not
bpref, as the principled incomplete-judgment answer. **[refuted — do not rely on bpref]**

---

## 5. Domain prior art: systematic review and e-discovery are our real analogues

The most useful realisation is that **policy evidence search is a high-recall TAR problem**, not a
web-search problem — and the systematic-review (Cochrane / CLEF eHealth TAR) and legal e-discovery
communities have already built the statistical machinery for "certify recall without a complete
gold set":

- **CLEF eHealth Technology-Assisted Review** tasks are the canonical academic benchmark for
  high-recall retrieval over biomedical literature, with the explicit objective of finding *all*
  relevant studies for a systematic review — the same near-total-recall objective a policy evidence
  review has. The harness machinery (active learning + stopping rule + recall estimate) is directly
  portable. (Practitioner/domain sources fetched; specific claims not in the verified top-25, so
  treat as orienting rather than load-bearing.)
- **Chao's estimator, QBCB, Webber's recall CIs (all §2)** *originate* in this tradition. They were
  built for exactly our problem: a low-prevalence relevant set in a large corpus, where missing
  relevant documents is costly and the true denominator is unknowable.
- **What transfers cleanly:** the statistics (capture–recapture, recall CIs, sample-based unbiased
  estimation, leave-out-uniques reusability tests).
  **What does not transfer for free:** the *relevance definition*. PICO-flavoured, grey-literature,
  geography/population-scoped policy relevance is an additional layer those benchmarks don't test.
  This is an argument for a *small policy-specific human-labelled anchor* (§6) rather than adopting
  an off-the-shelf biomedical TAR collection wholesale.

There is **no ready-made policy-document retrieval golden set** comparable to PaperFindingBench
that we found. Overton/GovInfo are corpora, not labelled retrieval benchmarks. So a bespoke
golden anchor is unavoidable if we want any absolute claim — the question is how to build the
cheapest defensible one.

---

## 6. Recommendations: highest-leverage use of a small annotation budget

The recurring theme of §1–§3 is that **everything rigorous needs *randomly sampled* human
judgments** — which the pool, by construction, does not contain. So the budget should buy a
sampling design, and the design should do triple duty.

### 6.1 Build one stratified human-labelled sample, designed to serve three goals

Stratify by the axes already in `queries.jsonl` — **use case × literature density** — plus a
within-pool stratification by **rank band and contributing arm** so the sample touches docs only
one arm found. For each sampled (query, paper), collect a human 0–3 label using the *same* criteria
the LLM judge sees (so the comparison is apples-to-apples).

This one sample then yields:

1. **Judge validation (§3).** Human vs LLM agreement — report Cohen's κ on the 0–3 labels *and*,
   more importantly, whether the LLM judge preserves the *system ranking* (the Thomas et al.
   validity criterion). This is what licenses every downstream LLM-judged number.
2. **Pool-bias / reusability diagnostic (§1).** Run **leave-one-arm-out Kendall's τ** (the modern
   group-aware form of leave-out-uniques): remove the relevant docs each arm *alone* contributed,
   re-rank, and measure how much the ladder moves. Historic TREC ad hoc collections treated
   ~0.5–2.2% movement as noise (reusable) and ~6–8% as problematic — gives us a concrete acceptance
   threshold to report. **[verified]**
3. **Absolute-recall anchor (§2).** On the random portion, compute a **beta-binomial recall CI
   (half-priors)** for a handful of headline queries — turning "recall 0.52" into "recall 0.52,
   95% CI [.., ..]." Optionally cross-check `k_est` against a **Chao** estimate of `|D+|` from
   arm-overlap (free; already have origin attribution).

> Whether a *single* sample can serve all three cleanly is the genuine open question: infAP/HT want
> a **uniform** random sample of the pool; leave-one-arm-out wants **stratified** coverage of
> arm-unique docs; QBCB wants a **positive-only** sample. A uniform random sample is the most
> reusable default and supports (1) and (3-CI); add a targeted stratified top-up for (2). Don't
> over-engineer this before the first pass tells you where the bias actually is.

### 6.2 Run the cross-family judge ablation (no new annotation needed)

Re-judge a stratified sample of the *existing cached pool* with a different model family and
recompute the ladder. This is the cheapest way to retire (or quantify) the coupling risk in §3.2,
and it needs zero human labels. **Do this first** — it's re-judge-only on cached evidence, and it
directly tests the assumption the whole relative-comparison claim rests on.

### 6.3 Reporting discipline (cheap, high credibility)

- Frame `recall@k_est` as a **relative ladder rung**, never an absolute coverage figure; restate
  the inflation cap in plain English (already planned).
- Keep the directions straight: pooled arms *over*-estimate recall (incomplete denominator); a
  future novel arm would be *under*-credited. **[verified]**
- Publish the leave-one-arm-out τ alongside the ladder as a reusability self-test.
- Never report a bare absolute recall point estimate — pair it with a CI (§2.3).
- Do **not** migrate the headline to bpref. **[refuted]**

### 6.4 What *not* to spend on yet (YAGNI)

Full QBCB certification, Horvitz–Thompson active-sampling infrastructure, and a classifier-based
de-biased judgment set (Büttcher et al. 2007) are all real and all overkill for a 26-query relative
experiment. They become relevant only if "certify absolute recall of the shipped product" turns
into a hard external requirement (e.g. a Cochrane-style guarantee for a published evidence review).
Note them as the escalation path; don't build them now.

---

## Appendix A — Sources

**Verified (3-0 adversarial, primary IR literature):**

- Buckley, Dimmick, Soboroff & Voorhees, *Bias and the Limits of Pooling for Large Collections*,
  Information Retrieval 2007 — https://link.springer.com/article/10.1007/s10791-007-9032-x
- Büttcher, Clarke, Yeung & Soboroff, *Reliable IR Evaluation with Incomplete and Biased
  Judgements*, SIGIR 2007 — https://dl.acm.org/doi/10.1145/1277741.1277755
- Buckley & Voorhees, *Retrieval Evaluation with Incomplete Information*, SIGIR 2004 —
  https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=150469
- Yilmaz, Craswell, Mitra & Campos, *On the Reliability of Test Collections for Evaluating Systems
  of Different Types*, SIGIR 2020 — https://arxiv.org/pdf/2004.13486
- Yilmaz & Aslam, *Estimating Average Precision When Judgments Are Incomplete* (infAP), KAIS 2008 —
  https://link.springer.com/article/10.1007/s10115-007-0101-7
- Li & Kanoulas, *Active Sampling for Large-scale IR Evaluation* (Horvitz–Thompson), CIKM 2017 —
  https://arxiv.org/pdf/1709.01709
- Bron et al., *Using Chao's Estimator as a Stopping Criterion for TAR*, ACM TOIS 2024/25 —
  https://dl.acm.org/doi/full/10.1145/3724116
- Webber, *Approximate Recall Confidence Intervals*, ACM TOIS 2013 — https://arxiv.org/pdf/1202.2880
- Lewis, Yang & Frieder, *Certifying One-Phase TAR* (PET bias, QBCB), CIKM 2021 —
  https://arxiv.org/pdf/2108.12746

**LLM-as-judge (abstract-level; full effect sizes not extracted):**

- Thomas, Spielman, Craswell & Mitra, *Large Language Models Can Accurately Predict Searcher
  Preferences* (UMBRELA lineage), arXiv 2309.10621 (2024) — https://arxiv.org/abs/2309.10621
- Wataoka, Takahashi & Ri, *Self-Preference Bias in LLM-as-a-Judge*, arXiv 2410.21819 (2024) —
  https://arxiv.org/abs/2410.21819
- Additional fetched-but-unverified LLM-judge sources: arXiv 2406.06519, 2412.17156;
  Balog (SIGIR 2025, https://krisztianbalog.com/files/sigir2025-llms.pdf — PDF did not parse).

**Domain/TAR (orienting; specific claims not in verified top-25):**

- CLEF eHealth TAR and systematic-review/e-discovery sources: https://dl.acm.org/doi/10.1007/978-3-031-42448-9_2,
  https://pmc.ncbi.nlm.nih.gov/articles/PMC12621535/,
  https://www.sciencedirect.com/science/article/abs/pii/S0895435611001107,
  https://dl.acm.org/doi/10.1145/2600428.2609601

## Appendix B — Refuted claims (do not rely on)

- bpref is *not* a safe drop-in for incomplete judgments here: the invariance claim was killed 0-3
  and the "τ > 0.9 down to 25–50% of judgments" robustness claim was killed 1-2. Use sample-based
  estimators (§2) instead.
- Do **not** cite the "infAP from 80% sample → Pearson 0.9996 / τ 0.986" accuracy figure (killed
  1-2). Use infAP's *unbiasedness* property qualitatively, not that specific number.

## Appendix C — Open questions worth a follow-up pass

1. How large is the LLM-judge self-preference effect *in our harness* — by how much does a
   gpt-5.x judge inflate the most stylistically-aligned arm's `recall@k_est` vs a cross-family
   judge? (Answer via §6.2 ablation + the Thomas/UMBRELA/Balog literature.)
2. Empirical LLM-vs-human agreement on *policy-domain, PICO-flavoured* relevance (incl. grey
   literature) — is a stratified human sample enough to calibrate the judge?
3. How does `k_est` (inflation heuristic) compare against a Chao lower-bound and a Webber
   beta-binomial CI on the *same* pooled data — does it systematically over- or under-estimate the
   relevant-set size?
4. Optimal split of a small annotation budget across uniform-random (infAP/CI), stratified-unique
   (leave-one-arm-out τ), and positive-only (QBCB) designs — can one sample serve all three?
