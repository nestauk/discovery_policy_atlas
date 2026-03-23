"""Clustering, LLM labelling, similarity analysis, and report builders.

Contains all analysis logic extracted from cluster_themes.py:
- BERTopic clustering
- LLM-powered cluster labelling and merge review
- Meta-theme assignment
- Cross-search duplicate detection
- Cluster report builders
"""

from __future__ import annotations

import json
import logging
import os
import re
import numpy as np
import pandas as pd

# Avoid noisy Hugging Face tokenizer fork warnings during local script runs.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from umap import UMAP

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SIMILARITY_THRESHOLD = 0.7

POSITIVE_VERDICTS = {
    "suggested_positive",
    "evidenced_positive",
    "well_evidenced_positive",
}

# Verdict colours — green gradient for positive (darker = stronger evidence),
# amber for contested, grey for insufficient/unknown.
VERDICT_COLORS = {
    "well_evidenced_positive": "#15803D",   # dark green
    "evidenced_positive": "#22C55E",        # green
    "suggested_positive": "#86EFAC",        # light green
    "contested": "#F59E0B",                 # amber
    "suggested_negative": "#FCA5A5",        # light red
    "evidenced_negative": "#EF4444",        # red
    "well_evidenced_negative": "#B91C1C",   # dark red
    "null_effect": "#9CA3AF",               # grey
    "insufficient_evidence": "#D1D5DB",     # light grey
}

# Display order: strongest positive first, then contested, then negative, then null
VERDICT_ORDER = [
    "well_evidenced_positive",
    "evidenced_positive",
    "suggested_positive",
    "contested",
    "suggested_negative",
    "evidenced_negative",
    "well_evidenced_negative",
    "null_effect",
    "insufficient_evidence",
]

# Evidence category colours and display order (strongest evidence first).
# Keyed by the category name as it appears in the exported spreadsheet.
EVIDENCE_CATEGORIES = [
    ("Systematic Review and Meta-Analysis", "#0F294A"),
    ("RCTs and Quasi-Experimental Studies", "#9A1BBE"),
    ("Observational Research Studies", "#0000FF"),
    ("Modelling & Simulation", "#18A48C"),
    ("Policy Syntheses & Guidance Documents", "#97D9E3"),
    ("Qualitative & Contextual Evidence", "#A59BEE"),
    ("Expert Opinion and Commentary", "#F6A4B7"),
    ("Other (Non-evidence documents)", "#F8F5F4"),
    ("Unknown / Insufficient information", "#F8F5F4"),
]

EVIDENCE_CATEGORY_COLORS = {name: color for name, color in EVIDENCE_CATEGORIES}
EVIDENCE_CATEGORY_ORDER = [name for name, _ in EVIDENCE_CATEGORIES]

TEAL_COLORSCALE = [
    [0.0, "rgb(255, 255, 255)"],
    [0.05, "rgb(224, 243, 235)"],
    [0.2, "rgb(178, 226, 210)"],
    [0.4, "rgb(127, 205, 187)"],
    [0.6, "rgb(65, 174, 158)"],
    [0.8, "rgb(29, 133, 126)"],
    [1.0, "rgb(1, 90, 94)"],
]

# Reference meta-themes — used as *suggestions* for grouping, not a closed set.
# The LLM may create additional themes if clusters don't fit these.
REFERENCE_META_THEMES: dict[str, str] = {
    "Early years & family foundations": (
        "Build resilience upstream by improving the conditions in which children grow up."
    ),
    "Mental health, behaviour & individual capability": (
        "Increase people's ability to regulate, learn, decide and persist under pressure."
    ),
    "Community resilience & social capital": (
        "Resilience in relationships, trust and local institutions."
    ),
    "Climate & place-based adaptation": (
        "Help places adapt to climate risk in ways that increase resilience "
        "and democratic legitimacy."
    ),
    "Digital & information resilience": (
        "Whether people and institutions can navigate digital systems safely and sovereignly."
    ),
    "Institutional & governance reform": (
        "Whether institutions can think long-term, act preventively and share power."
    ),
}

SEARCH_SHORT_NAMES = {
    "How to improve structural enabling conditions": "Structural Enabling",
    "How to achieve systemic reorientation": "Systemic Reorientation",
    "Interventions to improve institutional adaptive capacity": "Institutional Adaptive",
    "Interventions to improve collective self-governance": "Collective Self-Governance",
    "Interventions to improve community social capital": "Community Social Capital",
    "Interventions to improve community infrastructure": "Community Infrastructure",
    "Interventions to build or improve community safety nets": "Community Safety Nets",
    "Interventions targeting the capacities, resources, and conditions of individuals": "Individual/Family Capacities",
    "Interventions which improve individual adaptive capacity": "Individual Adaptive",
    "Interventions which address individual and family resource scarcity": "Individual/Family Resources",
    "Interventions reforming institutions, governance, and structural systems": "Governance Reform",
    "Interventions building collective capacity, social infrastructure": "Collective Capacity",
}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


class StaticTopicModel:
    """Minimal topic-model stub used when the corpus is too small to cluster."""

    def __init__(self, docs: list[str], topics: list[int]):
        self._docs = docs
        self._topics = topics

    def get_topic(self, cluster_id: int) -> list[tuple[str, float]]:
        if cluster_id == -1:
            return []

        tokens: list[str] = []
        for doc, topic in zip(self._docs, self._topics):
            if topic != cluster_id:
                continue
            tokens.extend(re.findall(r"[a-z0-9]+", doc.lower()))

        if not tokens:
            return []

        counts = pd.Series(tokens).value_counts().head(8)
        return [(token, float(count)) for token, count in counts.items()]


def shorten_search(title: str) -> str:
    """Map long search query titles to short readable names."""
    for prefix, short in SEARCH_SHORT_NAMES.items():
        if title.startswith(prefix):
            return short
    return title[:30]


def _get_openai_client():
    """Create an OpenAI client using the environment API key."""
    import openai
    return openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def _strip_markdown_codeblock(text: str) -> str:
    """Strip markdown code fences (```...```) from LLM responses."""
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return text


def _resolve_canonical(node: int, merge_map: dict[int, int]) -> int:
    """Follow the merge chain to find the canonical cluster ID."""
    while node in merge_map:
        node = merge_map[node]
    return node


def _format_distribution(series: pd.Series) -> str:
    """Format a value_counts Series as 'key: count, key: count, ...'."""
    return ", ".join(f"{k}: {v}" for k, v in series.value_counts().to_dict().items())


def slugify(text: str, max_len: int = 60) -> str:
    """Create a filesystem-safe slug from text."""
    import re
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:max_len]


def wrap_label(text: str, max_chars: int = 20) -> str:
    """Insert <br> to wrap long labels for Plotly axis display."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for w in words:
        if current and len(current) + 1 + len(w) > max_chars:
            lines.append(current)
            current = w
        else:
            current = f"{current} {w}" if current else w
    if current:
        lines.append(current)
    return "<br>".join(lines)


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------


def run_bertopic(
    docs: list[str],
    embedding_model: SentenceTransformer,
    min_cluster_size: int = 3,
    label: str = "items",
):
    """Run BERTopic clustering (TF-IDF keywords only, LLM labels applied after)."""
    if not docs:
        logger.info("%s: no documents after filtering; skipping clustering", label)
        return StaticTopicModel([], []), []

    min_docs_for_clustering = max(3, min_cluster_size)
    if len(docs) < min_docs_for_clustering:
        logger.warning(
            "%s: only %d docs after filtering; need at least %d for BERTopic. "
            "Marking all items as unclustered.",
            label,
            len(docs),
            min_docs_for_clustering,
        )
        topics = [-1] * len(docs)
        return StaticTopicModel(docs, topics), topics

    from bertopic import BERTopic
    from hdbscan import HDBSCAN

    umap_model = UMAP(
        n_neighbors=min(10, max(2, len(docs) - 1)),
        n_components=min(5, max(2, len(docs) // 10)),
        min_dist=0.0,
        metric="cosine",
        random_state=42,
    )

    hdbscan_model = HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=1,
        metric="euclidean",
        cluster_selection_method="leaf",
        prediction_data=True,
    )

    topic_model = BERTopic(
        embedding_model=embedding_model,
        umap_model=umap_model,
        hdbscan_model=hdbscan_model,
        min_topic_size=min_cluster_size,
        verbose=False,
    )

    topics, _ = topic_model.fit_transform(docs)

    n_clusters = len(set(topics)) - (1 if -1 in topics else 0)
    n_outliers = sum(1 for t in topics if t == -1)
    logger.info("%s: %d clusters, %d outliers out of %d docs", label, n_clusters, n_outliers, len(docs))

    return topic_model, topics


def get_tfidf_label(topic_model, cluster_id: int) -> str:
    """Get TF-IDF keyword label as fallback."""
    if cluster_id == -1:
        return "Unclustered"
    topic_words = topic_model.get_topic(cluster_id)
    if topic_words:
        return ", ".join(w for w, _ in topic_words[:5])
    return f"Cluster {cluster_id}"


# ---------------------------------------------------------------------------
# LLM labelling and merge review
# ---------------------------------------------------------------------------


def generate_llm_labels(
    topic_model,
    topics: list[int],
    docs: list[str],
    names: list[str],
) -> dict[int, str]:
    """Generate distinctive cluster labels using OpenAI.

    Sends ALL cluster summaries at once so the LLM can produce labels
    that are distinctive from each other, reflecting the actual content
    differences between similar-sounding clusters.
    """
    client = _get_openai_client()
    cluster_ids = sorted(set(t for t in topics if t != -1))
    labels = {-1: "Unclustered"}

    # Build cluster summaries
    cluster_summaries = {}
    for cid in cluster_ids:
        member_indices = [i for i, t in enumerate(topics) if t == cid]
        member_names = [names[i] for i in member_indices[:10]]
        member_descs = [docs[i][:250] for i in member_indices[:6]]

        topic_words = topic_model.get_topic(cid)
        keywords = ", ".join(w for w, _ in (topic_words or [])[:8])

        cluster_summaries[cid] = {
            "names": member_names,
            "descriptions": member_descs,
            "keywords": keywords,
        }

    # Build a single prompt with all clusters
    cluster_blocks = []
    for cid in cluster_ids:
        s = cluster_summaries[cid]
        block = (
            f"CLUSTER {cid} ({len(s['names'])} members):\n"
            f"  Members: {' | '.join(s['names'])}\n"
            f"  Sample descriptions:\n"
            + "\n".join(f"    - {d}" for d in s["descriptions"])
            + f"\n  Keywords: {s['keywords']}"
        )
        cluster_blocks.append(block)

    prompt = (
        f"You are labelling clusters from a policy research evidence analysis. "
        f"There are {len(cluster_ids)} clusters below. Your job is to give each "
        f"a short label (3-7 words) suitable as a category name in a policy report.\n\n"
        f"CRITICAL: Some clusters cover similar domains (e.g. multiple clusters "
        f"about mental health, or multiple about social cohesion). You MUST make "
        f"labels distinctive — capture what makes each cluster DIFFERENT from the "
        f"others, based on the actual member descriptions. For example, instead of "
        f"two clusters both called 'Mental Health and Wellbeing', use labels like "
        f"'Psychosocial Empowerment & Recovery' vs 'Cognitive Function & Resilience'.\n\n"
        + "\n\n".join(cluster_blocks)
        + "\n\nRespond with ONLY a JSON object mapping cluster ID to label, e.g.:\n"
        '{"0": "Label for cluster 0", "1": "Label for cluster 1", ...}'
    )

    try:
        response = client.chat.completions.create(
            model="gpt-5.4-mini",
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=500,
            temperature=0.3,
        )
        content = _strip_markdown_codeblock(response.choices[0].message.content.strip())
        result = json.loads(content)
        for cid in cluster_ids:
            key = str(cid)
            if key in result:
                labels[cid] = result[key].strip().strip('"')
            else:
                labels[cid] = cluster_summaries[cid]["keywords"][:50] or f"Cluster {cid}"
    except Exception as e:
        logger.warning("Batch labelling failed (%s), falling back to per-cluster", e)
        for cid in cluster_ids:
            s = cluster_summaries[cid]
            single_prompt = (
                "These are items in a cluster from a policy research analysis:\n\n"
                "Item names:\n" + "\n".join(f"- {n}" for n in s["names"]) + "\n\n"
                "Sample descriptions:\n" + "\n".join(f"- {d}" for d in s["descriptions"]) + "\n\n"
                f"Keywords: {s['keywords']}\n\n"
                "Give this cluster a short descriptive label (3-6 words) suitable as a "
                "category name in a policy report. Return ONLY the label."
            )
            try:
                resp = client.chat.completions.create(
                    model="gpt-5.4-mini",
                    messages=[{"role": "user", "content": single_prompt}],
                    max_completion_tokens=30,
                    temperature=0.3,
                )
                labels[cid] = resp.choices[0].message.content.strip().strip('"')
            except Exception:
                labels[cid] = s["keywords"][:50] if s["keywords"] else f"Cluster {cid}"

    return labels


def llm_merge_review(
    topics: list[int],
    names: list[str],
    docs: list[str],
    labels: dict[int, str],
    cluster_sim: pd.DataFrame,
    similarity_floor: float = 0.55,
) -> tuple[list[int], dict[int, str]]:
    """Ask an LLM to review high-similarity cluster pairs and merge where appropriate.

    Returns updated (topics, labels) with merged cluster IDs remapped.
    """
    client = _get_openai_client()

    candidates = cluster_sim[cluster_sim["Cosine Similarity"] >= similarity_floor].copy()
    if candidates.empty:
        logger.info("No cluster pairs above similarity floor — skipping merge review")
        return topics, labels

    # Build member lookup
    cluster_members: dict[int, list[str]] = {}
    cluster_descs: dict[int, list[str]] = {}
    for i, t in enumerate(topics):
        if t == -1:
            continue
        cluster_members.setdefault(t, []).append(names[i])
        cluster_descs.setdefault(t, []).append(docs[i][:300])

    # Ask LLM about each candidate pair
    merge_pairs: list[tuple[int, int]] = []
    for _, row in candidates.iterrows():
        c_a, c_b = int(row["Cluster A"]), int(row["Cluster B"])
        sim = row["Cosine Similarity"]
        label_a = labels.get(c_a, f"Cluster {c_a}")
        label_b = labels.get(c_b, f"Cluster {c_b}")
        members_a = cluster_members.get(c_a, [])
        members_b = cluster_members.get(c_b, [])
        descs_a = cluster_descs.get(c_a, [])[:6]
        descs_b = cluster_descs.get(c_b, [])[:6]

        prompt = (
            "You are reviewing clusters from a policy evidence analysis.\n\n"
            f"CLUSTER A: \"{label_a}\" (cosine similarity to B: {sim:.3f})\n"
            "Members:\n" + "\n".join(f"  - {n}" for n in members_a) + "\n"
            "Sample descriptions:\n" + "\n".join(f"  - {d}" for d in descs_a) + "\n\n"
            f"CLUSTER B: \"{label_b}\"\n"
            "Members:\n" + "\n".join(f"  - {n}" for n in members_b) + "\n"
            "Sample descriptions:\n" + "\n".join(f"  - {d}" for d in descs_b) + "\n\n"
            "Should these two clusters be MERGED into one? They would be merged if they "
            "describe essentially the same outcome domain, just with different phrasing. "
            "They should stay SEPARATE if they represent meaningfully different concepts "
            "(e.g. individual mental health vs community resilience, or clinical outcomes "
            "vs social outcomes).\n\n"
            "Respond with ONLY a JSON object: "
            '{"merge": true/false, "reason": "one sentence"}'
        )

        try:
            response = client.chat.completions.create(
                model="gpt-5.4-mini",
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=80,
                temperature=0.1,
            )
            content = _strip_markdown_codeblock(response.choices[0].message.content.strip())
            result = json.loads(content)
            should_merge = result.get("merge", False)
            reason = result.get("reason", "")
            action = "MERGE" if should_merge else "KEEP SEPARATE"
            logger.debug("[%.3f] %s ↔ %s: %s — %s", sim, label_a, label_b, action, reason)
            if should_merge:
                merge_pairs.append((c_a, c_b))
        except Exception as e:
            logger.warning("Merge review failed for %s↔%s: %s", c_a, c_b, e)

    if not merge_pairs:
        logger.info("No merges recommended")
        return topics, labels

    # Resolve transitive merges
    merge_map: dict[int, int] = {}
    for a, b in merge_pairs:
        canon_a = _resolve_canonical(a, merge_map)
        canon_b = _resolve_canonical(b, merge_map)
        if canon_a != canon_b:
            target, source = min(canon_a, canon_b), max(canon_a, canon_b)
            merge_map[source] = target

    new_topics = [_resolve_canonical(t, merge_map) for t in topics]

    # Generate new labels for merged clusters
    merged_cluster_ids = sorted(set(t for t in new_topics if t != -1))
    new_labels = {-1: "Unclustered"}
    for cid in merged_cluster_ids:
        source_ids = [cid] + [k for k, v in merge_map.items() if v == cid]
        if len(source_ids) == 1:
            new_labels[cid] = labels.get(cid, f"Cluster {cid}")
        else:
            all_members = []
            all_descs = []
            for sid in source_ids:
                all_members.extend(cluster_members.get(sid, []))
                all_descs.extend(cluster_descs.get(sid, [])[:3])

            prompt = (
                "These outcome themes have been merged into a single cluster:\n\n"
                "Members:\n" + "\n".join(f"- {n}" for n in all_members[:12]) + "\n\n"
                "Sample descriptions:\n" + "\n".join(f"- {d}" for d in all_descs[:6]) + "\n\n"
                "Give this merged cluster a short descriptive label (3-6 words) suitable "
                "as a category name in a policy report. Return ONLY the label."
            )
            try:
                response = client.chat.completions.create(
                    model="gpt-5.4-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_completion_tokens=30,
                    temperature=0.3,
                )
                new_labels[cid] = response.choices[0].message.content.strip().strip('"')
            except Exception:
                old_labels = [labels.get(sid, "") for sid in source_ids]
                new_labels[cid] = " / ".join(lb for lb in old_labels if lb)

            logger.debug("Merged %s → \"%s\"", source_ids, new_labels[cid])

    n_merges = len(set(merge_map.values()))
    n_absorbed = len(merge_map)
    logger.info("Applied %d merge(s) into %d target cluster(s)", n_absorbed, n_merges)
    return new_topics, new_labels


def assign_meta_themes(
    labels: dict[int, str],
    topics: list[int],
    docs: list[str],
    names: list[str],
) -> dict[int, str]:
    """Assign each cluster to a meta-theme using LLM.

    Uses REFERENCE_META_THEMES as suggestions but allows the LLM to create
    new themes if clusters don't fit the predefined ones.

    Returns:
        Tuple of (meta_map, new_theme_details) where meta_map maps cluster_id
        to meta-theme name, and new_theme_details maps emergent theme names to
        their definition and reasoning.
    """
    client = _get_openai_client()
    cluster_ids = sorted(cid for cid in set(topics) if cid != -1)

    cluster_blocks = []
    for cid in cluster_ids:
        member_indices = [i for i, t in enumerate(topics) if t == cid]
        member_names = [names[i] for i in member_indices[:8]]
        member_descs = [docs[i][:200] for i in member_indices[:4]]
        label = labels.get(cid, f"Cluster {cid}")
        block = (
            f"CLUSTER {cid} — \"{label}\" ({len(member_indices)} members):\n"
            f"  Members: {' | '.join(member_names)}\n"
            f"  Sample descriptions:\n"
            + "\n".join(f"    - {d}" for d in member_descs)
        )
        cluster_blocks.append(block)

    ref_lines = [f"  - \"{name}\": {desc}" for name, desc in REFERENCE_META_THEMES.items()]

    prompt = (
        "You are grouping fine-grained policy research clusters into higher-level "
        "thematic categories.\n\n"
        "Here are some REFERENCE themes (use these where they fit):\n"
        + "\n".join(ref_lines)
        + "\n\n"
        "IMPORTANT: These are suggestions, NOT a closed set. If a cluster clearly "
        "belongs to a domain not covered by the reference themes, create a NEW "
        "theme with a short name (3-7 words) and it will be included. Do not "
        "force-fit clusters into reference themes where they don't belong.\n\n"
        "Clusters to assign:\n\n"
        + "\n\n".join(cluster_blocks)
        + "\n\nRespond with ONLY a JSON object with two keys:\n"
        "1. \"assignments\": maps cluster ID to meta-theme name\n"
        "2. \"new_themes\": for any theme NOT in the reference list, provide an object with "
        "\"definition\" (one-sentence description like the reference themes) and "
        "\"reasoning\" (why no existing reference theme fits).\n\n"
        "Example:\n"
        '{\n'
        '  "assignments": {"0": "Community resilience & social capital", "1": "Economic security & livelihoods"},\n'
        '  "new_themes": {\n'
        '    "Economic security & livelihoods": {\n'
        '      "definition": "Strengthen household and community economic foundations to buffer against shocks.",\n'
        '      "reasoning": "Covers employment, income, and material security which span multiple reference themes without fitting neatly into any one."\n'
        '    }\n'
        '  }\n'
        '}'
    )

    meta_map: dict[int, str] = {-1: "Unclustered"}
    new_theme_details: dict[str, dict[str, str]] = {}
    try:
        response = client.chat.completions.create(
            model="gpt-5.4",
            messages=[{"role": "user", "content": prompt}],
            seed=49,
            max_completion_tokens=800,
        )
        content = _strip_markdown_codeblock(response.choices[0].message.content.strip())
        result = json.loads(content)

        assignments = result.get("assignments", result)
        new_theme_details = result.get("new_themes", {})

        for cid in cluster_ids:
            meta_map[cid] = assignments.get(str(cid), labels.get(cid, f"Cluster {cid}"))
    except Exception as e:
        logger.warning("Meta-theme assignment failed (%s), using cluster labels", e)
        for cid in cluster_ids:
            meta_map[cid] = labels.get(cid, f"Cluster {cid}")

    # Report assignments
    assigned_themes = sorted(set(v for k, v in meta_map.items() if k != -1))
    ref_names = set(REFERENCE_META_THEMES.keys())
    emergent = [t for t in assigned_themes if t not in ref_names]
    logger.info("Meta-themes: %d total, %d emergent", len(assigned_themes), len(emergent))
    for theme in assigned_themes:
        members = [labels.get(cid, "") for cid, t in meta_map.items() if t == theme and cid != -1]
        tag = " [NEW]" if theme in emergent else ""
        logger.debug("  %s%s: %s", theme, tag, ", ".join(members))
        if theme in new_theme_details:
            detail = new_theme_details[theme]
            logger.debug("    Definition: %s", detail.get("definition", "N/A"))
            logger.debug("    Reasoning: %s", detail.get("reasoning", "N/A"))

    return meta_map, new_theme_details


# ---------------------------------------------------------------------------
# Pairwise similarity
# ---------------------------------------------------------------------------


def find_cross_search_duplicates(
    df: pd.DataFrame,
    embeddings: np.ndarray,
    name_col: str,
    threshold: float,
) -> pd.DataFrame:
    """Find pairs of items from different searches with high cosine similarity."""
    columns = ["Item A", "Search A", "Item B", "Search B", "Cosine Similarity"]
    if len(df) < 2 or len(embeddings) < 2:
        return pd.DataFrame(columns=columns)

    sim_matrix = cosine_similarity(embeddings)
    searches = df["Project Title"].values
    names = df[name_col].values

    rows = []
    for i in range(len(df)):
        for j in range(i + 1, len(df)):
            if searches[i] == searches[j]:
                continue
            sim = sim_matrix[i, j]
            if sim >= threshold:
                rows.append({
                    "Item A": names[i],
                    "Search A": searches[i][:60],
                    "Item B": names[j],
                    "Search B": searches[j][:60],
                    "Cosine Similarity": round(float(sim), 3),
                })

    result = pd.DataFrame(rows, columns=columns)
    if not result.empty:
        result = result.sort_values("Cosine Similarity", ascending=False).reset_index(drop=True)
    return result


def compute_cross_cluster_similarity(
    topics: list[int], embeddings: np.ndarray,
) -> pd.DataFrame:
    """Compute pairwise cosine similarity between cluster centroids."""
    columns = ["Cluster A", "Cluster B", "Cosine Similarity"]
    cluster_ids = sorted(set(t for t in topics if t != -1))
    if len(cluster_ids) < 2:
        return pd.DataFrame(columns=columns)

    cluster_embeddings = {}
    for cid in cluster_ids:
        indices = [i for i, t in enumerate(topics) if t == cid]
        cluster_embeddings[cid] = embeddings[indices].mean(axis=0).reshape(1, -1)

    rows = []
    for i, c1 in enumerate(cluster_ids):
        for c2 in cluster_ids[i + 1:]:
            sim = cosine_similarity(cluster_embeddings[c1], cluster_embeddings[c2])[0][0]
            rows.append({"Cluster A": c1, "Cluster B": c2, "Cosine Similarity": round(sim, 3)})

    return (
        pd.DataFrame(rows, columns=columns)
        .sort_values("Cosine Similarity", ascending=False)
        .reset_index(drop=True)
    )


# ---------------------------------------------------------------------------
# Cluster report builders
# ---------------------------------------------------------------------------


def build_intervention_cluster_report(
    interventions: pd.DataFrame, topics: list[int], labels: dict[int, str],
) -> pd.DataFrame:
    """Build summary report of intervention clusters."""
    columns = [
        "Cluster ID",
        "Cluster Label",
        "Member Count",
        "Member Interventions",
        "Searches Contributing",
        "Search Count",
        "Total Source Documents",
        "Effect Consensus",
        "Geography Fit",
    ]
    interventions = interventions.copy()
    interventions["cluster_id"] = topics

    rows = []
    for cluster_id in sorted(set(topics)):
        cluster_df = interventions[interventions["cluster_id"] == cluster_id]
        members = cluster_df["Intervention Name"].tolist()
        searches = cluster_df["Project Title"].unique().tolist()
        total_source_docs = cluster_df["Source Documents"].sum()

        rows.append({
            "Cluster ID": cluster_id,
            "Cluster Label": labels.get(cluster_id, f"Cluster {cluster_id}"),
            "Member Count": len(cluster_df),
            "Member Interventions": " | ".join(members),
            "Searches Contributing": " | ".join(shorten_search(s) for s in searches),
            "Search Count": len(searches),
            "Total Source Documents": int(total_source_docs),
            "Effect Consensus": _format_distribution(cluster_df["Effect Consensus"]),
            "Geography Fit": _format_distribution(cluster_df["Geography Context Fit"]),
        })

    return pd.DataFrame(rows, columns=columns)


def build_outcome_cluster_report(
    outcomes: pd.DataFrame, topics: list[int], labels: dict[int, str],
    min_searches: int = 2,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build summary report of outcome clusters, split by cross-cutting vs single-search."""
    columns = [
        "Cluster ID",
        "Cluster Label",
        "Member Count",
        "Member Outcomes",
        "Searches Contributing",
        "Search Count",
        "Verdict Distribution",
        "Magnitude Distribution",
        "Mechanism Distribution",
        "Direction Distribution",
    ]
    outcomes = outcomes.copy()
    outcomes["cluster_id"] = topics

    cross_cutting_rows = []
    single_search_rows = []

    for cluster_id in sorted(set(topics)):
        cluster_df = outcomes[outcomes["cluster_id"] == cluster_id]
        members = cluster_df["Outcome Name"].tolist()
        searches = cluster_df["Project Title"].unique().tolist()

        row = {
            "Cluster ID": cluster_id,
            "Cluster Label": labels.get(cluster_id, f"Cluster {cluster_id}"),
            "Member Count": len(cluster_df),
            "Member Outcomes": " | ".join(members),
            "Searches Contributing": " | ".join(shorten_search(s) for s in searches),
            "Search Count": len(searches),
            "Verdict Distribution": _format_distribution(cluster_df["Verdict"]),
            "Magnitude Distribution": _format_distribution(cluster_df["Predicted Magnitude"]),
            "Mechanism Distribution": _format_distribution(cluster_df["Causal Mechanism"]),
            "Direction Distribution": _format_distribution(cluster_df["Effect Direction"]),
        }

        if len(searches) >= min_searches and cluster_id != -1:
            cross_cutting_rows.append(row)
        else:
            single_search_rows.append(row)

    return (
        pd.DataFrame(cross_cutting_rows, columns=columns),
        pd.DataFrame(single_search_rows, columns=columns),
    )


def build_member_detail_table(
    df: pd.DataFrame, topics: list[int], name_col: str, desc_col: str
) -> pd.DataFrame:
    """Build per-member detail table with cluster assignments."""
    detail = df[["Project Title", name_col, desc_col]].copy()
    detail["Cluster ID"] = topics
    detail = detail.sort_values(["Cluster ID", "Project Title"]).reset_index(drop=True)
    return detail
