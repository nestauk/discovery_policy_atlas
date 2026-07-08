"""Adaptive relevance-judging — Batched Thompson Sampling + short-circuit (spec §4.3 Step 2/4).

This is the closed loop that turns v2's open-loop "judge the top ~200" into "spend a fixed,
expensive judging budget where relevance is actually being found" (explainer
`docs/explainers/batched_thompson_sampling.md` §6). The re-mapping of the generic bandit onto
this pipeline is the thing to hold in your head:

    bandit arm        ->  a candidate ORIGIN ("keyword:q3", "dense:q1", "snowball_fwd:W12", ...)
    pulling an arm    ->  spending one LLM relevance-judgement on that origin's next candidate
    reward            ->  the judge's 0-3 level, passed through `to_reward` (exponential)
    budget / traffic  ->  the fixed judging quota (~250/query) — the scarce resource
    a batch           ->  a group of <=50 candidates judged before the next posterior update

Faithful PORT of PF's mechanism (`agents/.../dense/relevance_loading_optimization.py` +
`libs/dcollection/.../loaders/adaptive.py`), NOT of its plumbing. PF wraps AI2's *fork* of
`mabwiser` (`LearningPolicy.BatchedThompsonSampling`, a custom policy not in upstream mabwiser);
we reimplement the algorithm lightweight over our own `Candidate` (~1 file, no numpy/mabwiser
dep), which keeps it transparent, deterministic (seeded RNG), and instrumentable for the §4.7
origin-attribution analysis. The constants are frozen in `config.Adaptive`; the reward formula
and short-circuit are ported verbatim (those are deterministic and mechanism-critical).

> ★ What "batched" means here, precisely. While a batch is being ASSEMBLED, every origin's
> posterior is FROZEN — each pick is an independent Thompson draw from the stale posteriors, so
> the batch spreads across origins by probability-matching. Only AFTER the whole batch is judged
> do we fold its rewards back in (one posterior update). Batches grow geometrically
> (20 -> x2 -> capped at 50) so the number of "policy redeploys" is O(log budget).

REPL usage (no main()/argparse — spec conventions):
    import asyncio
    from core.adaptive import adaptive_load, HighlyRelevantShortcircuit, to_reward
    async def judge(batch):           # your judge sets cand.level in place
        for c in batch: c.level = ...
    sc = HighlyRelevantShortcircuit()
    judged, reason = asyncio.run(adaptive_load(candidates, judge, quota=150, shortcircuit=sc))
"""

from __future__ import annotations

import logging
import math
import random
from collections import deque
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Literal

from config import CONFIG
from core.source import Candidate

logger = logging.getLogger(__name__)

# A judge function judges a batch IN PLACE (sets cand.level). Async because the real judge
# (judge.py judge_papers) is async + batched; FakeSource tests pass a trivial async stub.
JudgeFn = Callable[[list[Candidate]], Awaitable[None]]

StopReason = Literal["quota", "exhausted", "short_circuit"]


# --------------------------------------------------------------------------- #
# Reward (PF loaders/adaptive.py:140-141, ported verbatim)
# --------------------------------------------------------------------------- #
def to_reward(level: int | None) -> float:
    """Map a 0-3 judge level to the bandit reward (PF `to_reward`): ((2**level)/8) - 0.125.

    EXPONENTIAL in the level, so the bandit is pulled hard toward origins yielding Perfects:
        level 0 -> 0.0     level 1 -> 0.125     level 2 -> 0.375     level 3 -> 0.875
    A Perfect (3) is worth ~2.3x a Highly (2) and 7x a Somewhat (1) — finding *Perfects* is
    what recall@k_est counts, so the reward shape matches the objective.
    """
    return ((2 ** float(level or 0)) / 8.0) - 0.125


# --------------------------------------------------------------------------- #
# Short-circuit (PF relevance_loading_optimization.py:56-85, ported)
# --------------------------------------------------------------------------- #
@dataclass
class HighlyRelevantShortcircuit:
    """Stop once >=1 Perfect (level 3) found AND accumulated score >= cap (PF).

    Scores +2 per distinct Perfect (level 3) and +1 per distinct Highly (level 2); levels 0-1
    contribute 0. "Distinct" = each paper counted once (dedup by paper_id), so re-seeing a
    paper across batches/iterations can't inflate the score. This is PF's actual stopping rule
    (spec §4.3/§4.3a, corrected 2026-06-17 from the earlier "+1/Somewhat" wording).
    """

    score_cap: int = CONFIG.adaptive.highly_relevant_cap
    _seen_ids: set[str] = field(default_factory=set)
    accumulated_score: float = 0.0
    found_perfect: bool = False

    def accumulate(self, judged: Iterable[Candidate]) -> HighlyRelevantShortcircuit:
        for c in judged:
            if (
                c.level is not None
                and c.level >= 2
                and c.paper_id not in self._seen_ids
            ):
                self._seen_ids.add(c.paper_id)
                self.accumulated_score += self._score_for_cap(c.level)
            if c.level == 3:
                self.found_perfect = True
        return self

    def should_break(self) -> bool:
        return self.found_perfect and self.accumulated_score >= self.score_cap

    @staticmethod
    def _score_for_cap(level: int) -> int:
        if level == 3:
            return CONFIG.adaptive.score_per_perfect  # +2
        if level == 2:
            return CONFIG.adaptive.score_per_highly  # +1
        return 0


# --------------------------------------------------------------------------- #
# Per-origin reward posterior (the bandit arm)
# --------------------------------------------------------------------------- #
@dataclass
class _ThompsonArm:
    """One origin's reward posterior: a windowed, decayed Normal over its mean reward.

    Models the depth-decay that motivates the whole design: an origin's yield FALLS as you read
    deeper into its ranked list (top is gold, page 3 is dross). So recent judgements weigh more
    (`decay_factor`) and only the last `window_size` count — when an origin's fresh rewards dry
    up, its posterior mean drops and the bandit abandons it. We model the posterior over the
    mean as Normal(weighted_mean, gaussian_variance / n_eff): more (effective) observations ->
    tighter posterior -> less exploration, the standard Thompson behaviour.
    """

    rewards: deque[float] = field(
        default_factory=lambda: deque(maxlen=CONFIG.adaptive.window_size)
    )

    def observe(self, reward: float) -> None:
        self.rewards.append(reward)

    def _weighted(self) -> tuple[float, float]:
        """(weighted_mean, n_eff) with the MOST RECENT reward weighted 1 and older ones
        discounted by decay_factor**age."""
        if not self.rewards:
            return 0.0, 0.0
        decay = CONFIG.adaptive.decay_factor
        # rewards[-1] is newest -> weight 1; rewards[-1-k] -> weight decay**k.
        weights = [decay**k for k in range(len(self.rewards) - 1, -1, -1)]
        n_eff = sum(weights)
        mean = sum(w * r for w, r in zip(weights, self.rewards)) / n_eff
        return mean, n_eff

    def sample(self, rng: random.Random) -> float:
        """Draw a Thompson sample from the posterior mean. Unobserved arms sample optimistically
        (large value) so they are explored first — though after the uniform preload every arm
        with candidates already has >=1 observation."""
        mean, n_eff = self._weighted()
        if n_eff <= 0:
            return math.inf
        sd = math.sqrt(CONFIG.adaptive.gaussian_variance / n_eff)
        return rng.gauss(mean, sd)


# --------------------------------------------------------------------------- #
# Origin assignment
# --------------------------------------------------------------------------- #
def assign_to_origins(candidates: Iterable[Candidate]) -> dict[str, list[Candidate]]:
    """Group candidates under EVERY origin that surfaced them (the bandit's arms).

    Faithful to PF's default `multi_group_by` (`relevance_loading_optimization.py:156`): a
    candidate co-surfaced by several origins is filed under EACH, so it is reachable from any of
    its arms. This is what prevents a relevant paper being STARVED — if it rode in on a cold
    origin but was *also* found by a hot one, the bandit reaches it via the hot arm rather than
    leaving it unjudged behind a queue that never gets pulled. The is-loaded guard in
    `adaptive_load` (the `claimed` set) then ensures a multi-filed candidate is judged exactly
    ONCE — charged to whichever arm pulls it first — so multi-membership costs no extra
    judgements.

    Origins are visited in sorted order for determinism; within an origin, input order is
    preserved = the source's own rank order (so preload + the bandit read the best-ranked
    candidates first, where the yield is highest). Candidates with no origin go under ""
    (shouldn't happen in the real pipeline; retrieval always tags origins).
    """
    by_origin: dict[str, list[Candidate]] = {}
    for c in candidates:
        for origin in sorted(c.origins) if c.origins else [""]:
            by_origin.setdefault(origin, []).append(c)
    return by_origin


# --------------------------------------------------------------------------- #
# The adaptive loop
# --------------------------------------------------------------------------- #
async def adaptive_load(
    candidates: list[Candidate],
    judge_fn: JudgeFn,
    *,
    quota: int,
    shortcircuit: HighlyRelevantShortcircuit | None = None,
    seed: int = 0,
) -> tuple[list[Candidate], StopReason]:
    """Judge candidates adaptively under a budget, steering toward high-reward origins.

    1. UNIFORM PRELOAD — judge up to `uniform_preload_size` from every origin, so no arm starts
       unexplored (PF `uniform_preload`).
    2. BTS BATCHES — assemble a geometrically-growing batch (20 -> x2 -> <= max_concurrency) by
       repeatedly Thompson-sampling the origins' (frozen) posteriors; judge the batch; then fold
       its rewards into the posteriors once.
    3. STOP when the quota is spent ("quota"), all candidates are judged ("exhausted"), or the
       short-circuit fires ("short_circuit").

    Returns (judged_candidates, stop_reason). Judges IN PLACE (sets cand.level) and only ever
    judges each candidate once. `seed` makes the Thompson draws reproducible.
    """
    rng = random.Random(seed)
    sc = shortcircuit or HighlyRelevantShortcircuit()
    cfg = CONFIG.adaptive

    by_origin = assign_to_origins(candidates)
    arms = {origin: _ThompsonArm() for origin in by_origin}
    # Per-origin read cursor into the (rank-ordered) candidate list.
    cursor = {origin: 0 for origin in by_origin}
    judged: list[Candidate] = []
    # Is-loaded guard (PF): a multi-origin candidate sits in several queues; `claimed` makes it
    # judged exactly ONCE, charged to whichever arm reaches it first. A candidate is claimed the
    # moment it is selected (preload or batch), so it is never double-pulled within a batch either.
    claimed: set[str] = set()

    def _next_from(origin: str) -> Candidate | None:
        queue = by_origin[origin]
        i = cursor[origin]
        while i < len(queue):  # skip candidates already claimed via another origin
            c = queue[i]
            i += 1
            if c.paper_id not in claimed:
                cursor[origin] = i
                claimed.add(c.paper_id)
                return c
        cursor[origin] = (
            i  # this queue's remaining are all claimed elsewhere -> exhausted
        )
        return None

    async def _judge_and_record(batch: list[Candidate]) -> None:
        await judge_fn(batch)
        judged.extend(batch)
        sc.accumulate(batch)

    # --- 1. Uniform preload ------------------------------------------------- #
    preload: list[tuple[str, Candidate]] = []
    for origin in by_origin:
        for _ in range(min(cfg.uniform_preload_size, quota - len(preload))):
            c = _next_from(origin)
            if c is None:
                break
            preload.append((origin, c))
        if len(preload) >= quota:
            break

    if preload:
        await _judge_and_record([c for _, c in preload])
        for origin, c in preload:  # posterior update after the preload "batch"
            arms[origin].observe(to_reward(c.level))
        if sc.should_break():
            logger.info("Short-circuit fired during preload (%d judged)", len(judged))
            return judged, "short_circuit"

    # --- 2. BTS batches ----------------------------------------------------- #
    batch_idx = 0
    while len(judged) < quota:
        live = [o for o in by_origin if cursor[o] < len(by_origin[o])]
        if not live:
            return judged, "exhausted"

        target = min(
            cfg.initial_batch_size * (cfg.batch_growth_factor**batch_idx),
            cfg.max_concurrency,
            quota - len(judged),
        )
        # Assemble the batch against FROZEN posteriors (probability-matching within the batch).
        # Carry (origin, candidate) pairs so the post-batch reward update knows each arm.
        batch: list[tuple[str, Candidate]] = []
        while len(batch) < target:
            live = [o for o in by_origin if cursor[o] < len(by_origin[o])]
            if not live:
                break
            origin = max(live, key=lambda o: arms[o].sample(rng))
            c = _next_from(origin)
            if c is not None:
                batch.append((origin, c))
        if not batch:
            return judged, "exhausted"

        await _judge_and_record([c for _, c in batch])
        for origin, c in batch:  # single posterior update after the batch
            arms[origin].observe(to_reward(c.level))
        if sc.should_break():
            logger.info("Short-circuit fired (%d judged)", len(judged))
            return judged, "short_circuit"
        batch_idx += 1

    return judged, "quota"
