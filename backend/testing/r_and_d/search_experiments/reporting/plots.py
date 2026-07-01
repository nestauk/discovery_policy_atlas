"""Per-arm distribution plots for the A/B/C metrics (Phase 9 companion to collect_results).

A strip+box of one per-query metric across the three arms, over the cross-arm **intersection**
(queries present in ALL arms) — paired, so per-query difficulty variance cancels. Dots = queries,
black diamond = mean, box line = median, box = IQR. Saves PNGs to results/plots/.

The per-query metric values come straight from `collect_results.collect` (same numbers as the
headline / summary.json), so plots never drift from the table. Distributions are typically
right-skewed (a few high-yield queries), so read the median (box line), not just the mean.

REPL usage (no main()/argparse — spec conventions):
    from plots import run_yield_plot, plot_metric_distribution, run_distribution_plots
    run_yield_plot()                              # Perfect-yield -> results/plots/yield_distribution.png
    plot_metric_distribution("recall_at_k_est")   # any metric key produced by arm_query_metrics
    run_distribution_plots()                       # the standard set (yield / recall / perfect_found)
"""

from __future__ import annotations

from pathlib import Path
from statistics import mean, median

import matplotlib
import numpy as np
from matplotlib.lines import Line2D

from reporting.collect_results import ARMS, collect, load_all_arms
from queries.loader import load_queries

# Headless backend: write PNGs, don't open windows. Must precede the pyplot import (override in a
# REPL with plt.switch_backend(...) if you want interactive show).
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402  (pyplot must import after use())

_PLOTS_DIR = (
    Path(__file__).resolve().parents[1] / "results" / "plots"
)  # parents[1]: results/ root is up one (reporting/)
_COLORS = {"arm_a": "#d62728", "arm_b": "#1f77b4", "arm_c": "#2ca02c"}

# Pretty y-axis labels for the metrics we plot most; falls back to the raw key otherwise.
_LABELS = {
    "yield_perfect_per_judged": "Perfect-yield  (perfect_found / n_judged)",
    "recall_at_k_est": "recall@k_est",
    "perfect_found": "Perfects found",
    "ndcg": "corrected nDCG",
    "adjusted_f1": "adjusted F1",
    "n_judged": "papers judged",
    "n_retrieved": "papers retrieved",
    # Parallel "Highly Relevant and above" (level >= 2) cutoff — siblings of the Perfect metrics.
    "yield_highly_per_judged": "Highly+-yield  (highly_found / n_judged)",
    "recall_at_k_est_highly": "recall@k_est  (Highly+)",
    "highly_found": "Highly+ found  (level ≥ 2)",
}

# The three metrics the user plots at both cutoffs, paired (Perfect key, Highly+ key).
_YIELD_RECALL_FOUND = (
    ("yield_perfect_per_judged", "yield_highly_per_judged"),
    ("recall_at_k_est", "recall_at_k_est_highly"),
    ("perfect_found", "highly_found"),
)


def intersection_qids(by_arm: dict) -> list[str]:
    """Query ids present in ALL arms — the paired comparison set (drops any arm-incomplete query)."""
    present = {arm: set(by_arm.get(arm, {})) for arm in ARMS}
    return [
        q.query_id
        for q in load_queries()
        if all(q.query_id in present[a] for a in ARMS)
    ]


def metric_by_arm(
    metric: str, by_arm: dict | None = None
) -> tuple[list[str], dict[str, list[float]]]:
    """Per-query `metric` values per arm over the intersection. Returns (qids, {arm: [values]}).

    `metric` is any key from `collect_results.arm_query_metrics` (e.g. recall_at_k_est,
    perfect_found, yield_perfect_per_judged, n_judged, ndcg, precision_at_25).
    """
    by_arm = by_arm if by_arm is not None else load_all_arms()
    qids = intersection_qids(by_arm)
    pq = collect(by_arm)["per_query"]
    values = {arm: [pq[q]["arms"][arm][metric] for q in qids] for arm in ARMS}
    return qids, values


def plot_metric_distribution(
    metric: str = "yield_perfect_per_judged",
    *,
    by_arm: dict | None = None,
    out: Path | None = None,
) -> Path:
    """Strip+box of `metric` per arm over the intersection. Returns the PNG path it wrote."""
    qids, values = metric_by_arm(metric, by_arm)
    label = _LABELS.get(metric, metric)
    rng = np.random.default_rng(0)  # deterministic jitter

    fig, ax = plt.subplots(figsize=(7, 5))
    positions = list(range(1, len(ARMS) + 1))
    ax.boxplot(
        [values[a] for a in ARMS],
        positions=positions,
        widths=0.5,
        showfliers=False,
        medianprops=dict(color="black"),
    )
    for pos, arm in zip(positions, ARMS):
        ys = values[arm]
        xs = pos + rng.uniform(-0.12, 0.12, size=len(ys))
        ax.scatter(xs, ys, color=_COLORS[arm], alpha=0.7, s=40, zorder=3)
        ax.scatter([pos], [mean(ys)], marker="D", color="black", s=55, zorder=4)

    ax.legend(
        handles=[
            Line2D(
                [],
                [],
                marker="D",
                color="black",
                linestyle="None",
                markersize=8,
                label="mean",
            ),
            Line2D([], [], color="black", linestyle="-", label="median (box line)"),
        ],
        loc="upper right",
    )
    ax.set_xticks(positions)
    ax.set_xticklabels(ARMS)
    ax.set_ylabel(label)
    ax.set_title(
        f"Per-query {label} by arm (n={len(qids)} intersection)\n"
        "box = IQR/median, diamond = mean, dots = queries"
    )
    ax.set_ylim(bottom=0)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()

    out = out or _PLOTS_DIR / f"{metric}_distribution.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


def plot_retrieved_vs_judged(
    *, by_arm: dict | None = None, out: Path | None = None
) -> Path:
    """Per-query retrieved vs judged, faceted one panel per arm (lollipop: stem judged->retrieved).

    Each panel's queries are sorted by retrieved desc (so the panel reads as a descending pool
    curve with the judged count underneath). The gap = pool the judge budget did NOT cover; a
    dashed line marks Arm A's judge_quota cap (Arm B/C judge adaptively, so their gap is the loop
    curtailing, not the quota). Over the cross-arm intersection so panel n matches the other plots.
    """
    from config import CONFIG  # judge_quota for the cap reference line

    by_arm = by_arm if by_arm is not None else load_all_arms()
    qids, retrieved = metric_by_arm("n_retrieved", by_arm)
    _, judged = metric_by_arm("n_judged", by_arm)
    quota = CONFIG.budgets.judge_quota

    fig, axes = plt.subplots(1, len(ARMS), figsize=(5 * len(ARMS), 5), sharey=True)
    for ax, arm in zip(axes, ARMS):
        order = sorted(range(len(qids)), key=lambda i: retrieved[arm][i], reverse=True)
        ret = [retrieved[arm][i] for i in order]
        jud = [judged[arm][i] for i in order]
        xs = list(range(len(order)))
        ax.vlines(xs, jud, ret, color=_COLORS[arm], alpha=0.35, lw=2, zorder=1)
        ax.scatter(
            xs,
            ret,
            facecolors="none",
            edgecolors=_COLORS[arm],
            s=42,
            zorder=3,
            label="retrieved",
        )
        ax.scatter(xs, jud, color=_COLORS[arm], s=42, zorder=3, label="judged")
        ax.axhline(quota, ls="--", color="grey", lw=1, alpha=0.8)
        ax.text(
            0,
            quota,
            f" judge_quota={quota}",
            color="grey",
            va="bottom",
            ha="left",
            fontsize=8,
        )
        ax.set_title(arm)
        ax.set_xlabel("queries (sorted by retrieved)")
        ax.grid(axis="y", alpha=0.3)
        ax.legend(loc="upper right", fontsize=8)
    axes[0].set_ylabel("papers")
    fig.suptitle(
        f"Retrieved (open) vs judged (filled) per query, by arm (n={len(qids)} intersection)"
    )
    fig.tight_layout()

    out = out or _PLOTS_DIR / "retrieved_vs_judged.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


# --------------------------------------------------------------------------- #
# Latency (per-arm stage breakdown — standalone model)
# --------------------------------------------------------------------------- #
_LATENCY_BUCKETS = ("formulate", "retrieve", "snowball", "rerank", "judge", "other")
_BUCKET_COLORS = {
    "formulate": "#9467bd",  # LLM: formulate/reformulate/suggest
    "retrieve": "#1f77b4",  # API: keyword/dense search
    "snowball": "#ff7f0e",  # API: citations/references
    "rerank": "#8c564b",  # API: cohere
    "judge": "#2ca02c",  # LLM: relevance judging (reconstructed standalone)
    "other": "#7f7f7f",  # dedupe/BTS/setup remainder
}


def _arm_timings(by_arm: dict, arm: str) -> list[tuple[str, dict]]:
    """[(qid, timings)] for queries where this arm persisted a timings record (skips old runs)."""
    return [
        (qid, rec["timings"])
        for qid, rec in by_arm.get(arm, {}).items()
        if rec.get("timings")
    ]


def estimate_judge_rate(by_arm: dict) -> float:
    """Cold per-paper judge wall-seconds. Judging is cross-arm cached, so per query the arm with the
    LARGEST judge_s did the most COLD judging; rate_q = that judge_s ÷ its n_judged. Median over
    queries. (The first arm run per query judges its whole pool cold, so this recovers the true
    cold rate without hard-coding run order.)"""
    qids = {qid for arm in ARMS for qid, _ in _arm_timings(by_arm, arm)}
    rates = []
    for qid in qids:
        best = (
            None  # (judge_s, n_judged) of the arm that judged most cold for this query
        )
        for arm in ARMS:
            rec = by_arm.get(arm, {}).get(qid)
            t = rec.get("timings") if rec else None
            if not t or not t.get("n_judged"):
                continue
            if best is None or t["judge_s"] > best[0]:
                best = (t["judge_s"], t["n_judged"])
        if best and best[0] > 0 and best[1] > 0:
            rates.append(best[0] / best[1])
    return median(rates) if rates else 0.0


def standalone_latency(
    by_arm: dict, judge_rate: float | None = None
) -> tuple[dict[str, dict[str, float]], float]:
    """Per-arm mean stage seconds for a STANDALONE deployment (the cross-arm judge cache doesn't
    exist in production, so each arm is charged for judging its OWN pool). Non-judge buckets are
    measured; `judge` is reconstructed as `n_judged × judge_rate` (cold per-paper rate, so it's not
    contaminated by which arm happened to hit the cache). Returns ({arm: {bucket: mean_s}}, rate)."""
    judge_rate = estimate_judge_rate(by_arm) if judge_rate is None else judge_rate
    out: dict[str, dict[str, float]] = {}
    for arm in ARMS:
        ts = _arm_timings(by_arm, arm)
        if not ts:
            continue
        agg = {b: 0.0 for b in _LATENCY_BUCKETS}
        for _qid, t in ts:
            for b in _LATENCY_BUCKETS:
                if b == "judge":
                    agg["judge"] += (t.get("n_judged", 0) or 0) * judge_rate
                else:
                    agg[b] += t.get(f"{b}_s", 0.0)
        out[arm] = {b: v / len(ts) for b, v in agg.items()}
    return out, judge_rate


def plot_latency(
    *,
    by_arm: dict | None = None,
    judge_rate: float | None = None,
    out: Path | None = None,
) -> Path | None:
    """Stacked per-arm latency by stage (standalone model). Needs `timings` in the persisted results
    (re-run run_experiment.py with the instrumented arms first); returns None if absent."""
    by_arm = by_arm if by_arm is not None else load_all_arms()
    per_arm, rate = standalone_latency(by_arm, judge_rate)
    if not per_arm:
        print(
            "plot_latency: no `timings` in persisted results — re-run run_experiment.py with the "
            "instrumented arms first (old runs predate latency capture)."
        )
        return None

    arms = [a for a in ARMS if a in per_arm]
    x = list(range(len(arms)))
    fig, ax = plt.subplots(figsize=(8, 5))
    bottoms = [0.0] * len(arms)
    for b in _LATENCY_BUCKETS:
        vals = [per_arm[a][b] for a in arms]
        ax.bar(x, vals, bottom=bottoms, label=b, color=_BUCKET_COLORS[b])
        bottoms = [bottoms[i] + vals[i] for i in range(len(arms))]
    ax.set_xticks(x)
    ax.set_xticklabels(arms)
    ax.set_ylabel("mean wall-seconds / query (standalone)")
    ax.set_title(
        f"Per-arm latency by stage (standalone; judge reconstructed @ {rate:.3f}s/paper)\n"
        "judge = n_judged × cold per-paper rate; other = dedupe/BTS/setup"
    )
    ax.legend(loc="upper left", fontsize=8, ncol=2)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    out = out or _PLOTS_DIR / "latency_by_stage.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


def run_yield_plot() -> Path:
    """The Perfect-yield distribution (kept at the stable filename we've been iterating on)."""
    return plot_metric_distribution(
        "yield_perfect_per_judged", out=_PLOTS_DIR / "yield_distribution.png"
    )


def run_distribution_plots(
    metrics: tuple[str, ...] = (
        "yield_perfect_per_judged",
        "recall_at_k_est",
        "perfect_found",
    ),
) -> list[Path]:
    """Generate the standard set of per-arm distribution plots; returns the PNG paths."""
    by_arm = load_all_arms()  # load once, reuse across metrics
    paths = [run_yield_plot()]
    paths += [
        plot_metric_distribution(m, by_arm=by_arm)
        for m in metrics
        if m != "yield_perfect_per_judged"
    ]
    paths.append(plot_retrieved_vs_judged(by_arm=by_arm))
    return paths


def run_highly_relevant_plots() -> list[Path]:
    """The three headline distributions at the relaxed 'Highly Relevant and above' (level>=2) cutoff:
    Highly+-yield, recall@k_est (Highly+), Highly+ found. Siblings of run_distribution_plots' Perfect
    versions — same plot, relaxed relevance bar (retrospective; no re-run)."""
    by_arm = load_all_arms()
    return [
        plot_metric_distribution(highly_key, by_arm=by_arm)
        for _perfect_key, highly_key in _YIELD_RECALL_FOUND
    ]


# --------------------------------------------------------------------------- #
# Cost ($) by stage — the dollar twin of plot_latency. Unlike latency, this needs NO `timings`:
# cost is reconstructed from the persisted n_judged (reporting.cost), so it plots existing runs.
# --------------------------------------------------------------------------- #
_COST_COMPONENTS = ("judge_usd", "boolean_usd", "llm_usd", "rerank_usd")
_COST_COLORS = {
    "judge_usd": "#9467bd",
    "boolean_usd": "#2ca02c",
    "llm_usd": "#ff7f0e",
    "rerank_usd": "#8c564b",
}
_COST_LABELS = {
    "judge_usd": "judge (gpt-5.4-mini)",
    "boolean_usd": "boolean formulation (gpt-4.1)",
    "llm_usd": "gpt-5.5",
    "rerank_usd": "cohere",
}


def plot_cost(
    *,
    by_arm: dict | None = None,
    judge_out: int | None = None,
    per_query: bool = False,
    out: Path | None = None,
) -> Path:
    """Stacked per-arm $ by component (judge / gpt-4.1 boolean / gpt-5.5 / rerank), attributed view.

    Cost is reconstructed from persisted n_judged + reporting.cost rates — works on any completed
    run with no `timings` and no re-run. `judge_out` overrides the judge output-token assumption
    (defaults to reporting.cost.JUDGE_OUT_TOKENS); pass JUDGE_OUT_TOKENS_SAFE for the upper estimate.
    `per_query=True` divides each arm by its own query count — the fair cross-arm view, since the
    arms ran different numbers of queries (A=23, B=22, C=24 in the current run).
    """
    from reporting.cost import JUDGE_OUT_TOKENS, attributed_costs

    by_arm = by_arm if by_arm is not None else load_all_arms()
    jo = judge_out if judge_out is not None else JUDGE_OUT_TOKENS
    costs = attributed_costs(by_arm, judge_out=jo)

    arms = [a for a in ARMS if costs.get(a, {}).get("n_queries")]
    denom = {a: (costs[a]["n_queries"] if per_query else 1) for a in arms}
    x = list(range(len(arms)))
    fig, ax = plt.subplots(figsize=(8, 5))
    bottoms = [0.0] * len(arms)
    for comp in _COST_COMPONENTS:
        vals = [costs[a][comp] / denom[a] for a in arms]
        ax.bar(
            x, vals, bottom=bottoms, label=_COST_LABELS[comp], color=_COST_COLORS[comp]
        )
        bottoms = [bottoms[i] + vals[i] for i in range(len(arms))]
    for i, a in enumerate(arms):  # total label above each bar
        ax.text(
            i,
            bottoms[i],
            f" ${costs[a]['total_usd'] / denom[a]:.2f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    ax.set_xticks(x)
    ax.set_xticklabels(arms)
    ax.set_ylabel("$ per query (mean)" if per_query else "$ (attributed / standalone)")
    scope = "mean cost / query" if per_query else "total cost (standalone)"
    ax.set_title(
        f"Per-arm {scope} by component (judge_out={jo} tokens)\n"
        "judge = n_judged × per-paper rate; reconstructed from persisted results"
    )
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    out = out or _PLOTS_DIR / ("cost_per_query.png" if per_query else "cost_by_arm.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out
