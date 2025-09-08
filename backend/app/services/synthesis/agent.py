from __future__ import annotations


import asyncio
from typing import List, TypedDict, Dict, Tuple, Optional, Any

from langgraph.graph import StateGraph, END

# Schemas for responses and interim state
from app.services.synthesis.schemas import Finding, KeyIssue, PolicyIntervention
from app.services.vectorization import vectorization_service
import json

# numpy import removed - no longer needed for LLM-based clustering
from langchain_core.prompts import ChatPromptTemplate
from app.utils.llm.llm_utils import get_llm
from app.core.config import settings
import numpy as np
from pydantic import BaseModel, Field

try:
    from hdbscan import HDBSCAN as HDBSCANLib  # type: ignore
except Exception:
    HDBSCANLib = None


async def postprocess_labels(state: SynthesisState) -> SynthesisState:
    """Post-process theme names and collapse near-duplicates by semantic similarity.

    - Normalises names (already applied in label step, kept idempotent).
    - Collapses near-duplicate labels if cosine similarity between embeddings >= 0.90.
    """
    print("---POSTPROCESSING LABELS---")
    issue_names = dict(state.get("issue_theme_names", {}) or {})
    intr_names = dict(state.get("intervention_theme_names", {}) or {})
    issue_clusters = dict(state.get("issue_clusters", {}) or {})
    intr_clusters = dict(state.get("intervention_clusters", {}) or {})

    async def _embed(text: str) -> List[float]:
        try:
            return await vectorization_service.generate_embedding(text)
        except Exception:
            return []

    async def _collapse(
        names: Dict[int, str], clusters: Dict[int, List[str]]
    ) -> Tuple[Dict[int, str], Dict[int, List[str]]]:
        if not names:
            return names, clusters
        ids = list(names.keys())
        texts = [names[i] for i in ids]
        embs = await asyncio.gather(*[_embed(t) for t in texts])

        # Cosine similarity matrix (sparse logic by threshold)
        def cos(a: List[float], b: List[float]) -> float:
            va = np.array(a)
            vb = np.array(b)
            na = np.linalg.norm(va) or 1.0
            nb = np.linalg.norm(vb) or 1.0
            return float(np.dot(va, vb) / (na * nb))

        threshold = 0.93
        parent: Dict[int, int] = {}
        for i in range(len(ids)):
            pi = ids[i]
            parent[pi] = pi

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                if embs[i] and embs[j] and cos(embs[i], embs[j]) >= threshold:
                    union(ids[i], ids[j])
        # Rebuild clusters and names
        rep_map: Dict[int, int] = {}
        for cid in ids:
            rep_map[cid] = find(cid)
        new_clusters: Dict[int, List[str]] = {}
        new_names: Dict[int, str] = {}
        for cid in ids:
            rep = rep_map[cid]
            new_clusters.setdefault(rep, [])
            new_clusters[rep].extend(clusters.get(cid, []))
            if rep not in new_names:
                new_names[rep] = names.get(rep, names.get(cid, ""))
        # De-duplicate concepts per merged cluster
        for k, v in list(new_clusters.items()):
            seen = set()
            uniq = []
            for s in v:
                if s not in seen:
                    seen.add(s)
                    uniq.append(s)
            new_clusters[k] = uniq
        return new_names, new_clusters

    issue_names, issue_clusters = await _collapse(issue_names, issue_clusters)
    intr_names, intr_clusters = await _collapse(intr_names, intr_clusters)

    return {
        "issue_theme_names": issue_names,
        "intervention_theme_names": intr_names,
        "issue_clusters": issue_clusters,
        "intervention_clusters": intr_clusters,
    }


class Concept(BaseModel):
    """Represents a concept with a canonical description and embedding."""

    id: str
    canonical_description: str
    kind: str = Field(description="'issue' or 'intervention'")
    embedding: List[float] = Field(default_factory=list)


class SynthesisState(TypedDict, total=False):
    """Represents the state of the synthesis agent workflow.

    Fields are intentionally permissive at this stage to allow
    incremental evolution of the agent without breaking changes.
    """

    project_id: str
    research_question: str
    raw_findings: List[Finding]
    aggregated_summary: Dict[str, List]
    executive_briefing: str
    # New fields for the extended workflow
    raw_extractions: List[Dict[str, Any]]
    concepts: List[Concept]
    outlier_concept_ids: List[str]
    issue_clusters: Dict[int, List[str]]
    intervention_clusters: Dict[int, List[str]]
    issue_theme_names: Dict[int, str]
    intervention_theme_names: Dict[int, str]
    theme_iteration: int
    finding_to_theme_map: Dict[str, Dict[str, str]]
    extraction_text_by_id: Dict[str, str]
    theme_critique: Optional[str]
    critique_notes: str
    justifications: Dict[str, List[str]]
    aggregated_issues: List[KeyIssue]
    aggregated_interventions: List[PolicyIntervention]


async def fetch_project_data(state: SynthesisState) -> SynthesisState:
    """Fetch initial data (e.g. research question and raw findings) for a project.

    For the initial scaffolding step, this uses placeholder values without
    hitting the database. Future iterations will populate these values from
    the persistence layer (e.g. Supabase/SQLAlchemy).
    """
    print("---FETCHING PROJECT DATA---")
    project_id = state["project_id"]

    supabase = vectorization_service.supabase

    # Load project (to get research question/query)
    project_res = (
        supabase.table("analysis_projects").select("*").eq("id", project_id).execute()
    )
    if not project_res.data:
        raise ValueError(f"Project with ID {project_id} not found")
    project = project_res.data[0]
    research_question = project.get("query") or "Not specified"

    # Load documents for the project
    docs_res = (
        supabase.table("analysis_documents")
        .select("*")
        .eq("analysis_project_id", project_id)
        .execute()
    )
    documents = docs_res.data or []

    findings: List[Finding] = _flatten_all_findings(documents)

    return {"research_question": research_question, "raw_findings": findings}


async def load_raw_extractions(state: SynthesisState) -> SynthesisState:
    """Load raw extractions for issues and interventions for a project."""
    print("---LOADING RAW EXTRACTIONS---")
    project_id = state.get("project_id", "")
    if not project_id:
        return {"raw_extractions": []}

    supabase = vectorization_service.supabase
    res = (
        supabase.table("analysis_extractions")
        .select(
            "id, analysis_document_id, extraction_type, label, description, raw_data"
        )
        .eq("analysis_project_id", project_id)
        .execute()
    )
    rows: List[Dict[str, Any]] = res.data or []

    def to_uniform(row: Dict[str, Any]) -> Dict[str, Any]:
        et = str(row.get("extraction_type") or "")
        raw = row.get("raw_data") or {}
        if et == "intervention":
            return {
                "id": str(row.get("id")),
                "type": "intervention",
                "intervention_name": str(row.get("label") or raw.get("name") or ""),
                "intervention_type": str(
                    raw.get("study_type") or raw.get("type") or ""
                ),
                "description": str(
                    row.get("description") or raw.get("description") or ""
                ),
            }
        elif et == "issue":
            return {
                "id": str(row.get("id")),
                "type": "issue",
                "issue_label": str(row.get("label") or raw.get("label") or ""),
                "explanation": str(
                    raw.get("explanation") or row.get("description") or ""
                ),
            }
        return {"id": str(row.get("id")), "type": et}

    uniform = [to_uniform(r) for r in rows]
    print(f"Loaded {len(uniform)} extractions")
    return {"raw_extractions": uniform}


async def create_canonical_concepts(state: SynthesisState) -> SynthesisState:
    """Generate canonical descriptions and embeddings from raw extractions."""
    print("---CREATING CANONICAL CONCEPTS AND EMBEDDINGS---")
    raw: List[Dict[str, Any]] = state.get("raw_extractions", []) or []
    if not raw:
        return {"concepts": []}

    def generate_description(ext: Dict[str, Any]) -> Tuple[str, str]:
        if ext.get("type") == "intervention":
            desc = (
                f"Intervention: {ext.get('intervention_name', '').strip()}. "
                f"Type: {ext.get('intervention_type', '').strip()}. "
                f"Description: {ext.get('description', '').strip()}"
            ).strip()
            return "intervention", desc
        if ext.get("type") == "issue":
            desc = (
                f"Issue: {ext.get('issue_label', '').strip()}. "
                f"Explanation: {ext.get('explanation', '').strip()}"
            ).strip()
            return "issue", desc
        return "", ""

    items: List[Tuple[str, str, str]] = []  # (id, kind, description)
    for r in raw:
        kind, desc = generate_description(r)
        if desc:
            items.append((str(r.get("id")), kind, desc))

    async def _embed_one(text: str) -> List[float]:
        try:
            return await vectorization_service.generate_embedding(text)
        except Exception:
            return []

    # Deduplicate descriptions to reduce redundant embeddings while preserving ID mappings
    description_to_ids: Dict[str, List[str]] = {}
    description_to_kind: Dict[str, str] = {}
    for cid, kind, desc in items:
        description_to_ids.setdefault(desc, []).append(cid)
        if desc not in description_to_kind:
            description_to_kind[desc] = kind

    unique_descriptions = list(description_to_ids.keys())
    embeddings: List[List[float]] = await asyncio.gather(
        *[_embed_one(desc) for desc in unique_descriptions]
    )

    # Build concept list using a representative id for each unique description
    concepts: List[Concept] = []
    for desc, emb in zip(unique_descriptions, embeddings):
        rep_id = description_to_ids.get(desc, [desc])[0]
        kind = description_to_kind.get(desc, "")
        concepts.append(
            Concept(
                id=rep_id,
                kind=kind or "",
                canonical_description=desc,
                embedding=emb or [],
            )
        )

    extraction_text_by_id = {}
    for desc, ids in description_to_ids.items():
        for eid in ids:
            extraction_text_by_id[eid] = desc

    print(f"Created {len(concepts)} unique concepts (from {len(items)} extractions)")
    return {
        **state,
        "concepts": concepts,
        "extraction_text_by_id": extraction_text_by_id,
        "description_to_ids": description_to_ids,
    }


def _flatten_all_findings(documents: List[dict]) -> List[Finding]:
    """Flatten findings across all documents without filtering.

    Mirrors the structure used in the legacy service, but returns all results.
    """
    all_findings: List[Finding] = []
    for doc in documents:
        extraction_results = doc.get("extraction_results") or {}
        if not extraction_results:
            continue

        interventions = extraction_results.get("interventions", []) or []
        results = extraction_results.get("results", []) or []

        # Map intervention index → intervention object
        intr_by_idx = {
            int(i.get("idx")): i
            for i in interventions
            if i is not None and i.get("idx") is not None
        }

        for res in results:
            try:
                intr_idx = int(res.get("intervention_idx"))
            except Exception:
                continue

            intr = intr_by_idx.get(intr_idx) or {}

            evidence_items: List[str] = []
            intr_quote = intr.get("supporting_quote")
            if intr_quote:
                evidence_items.append(str(intr_quote))
            res_quote = res.get("supporting_quote")
            if res_quote:
                evidence_items.append(str(res_quote))
            res_text = res.get("result_text")
            if res_text and str(res_text) not in evidence_items:
                evidence_items.append(str(res_text))

            finding = Finding(
                SourceTitle=str(doc.get("title") or "Unknown Source"),
                Source=str(doc.get("source") or "") or None,
                DocId=str(doc.get("doc_id") or doc.get("id") or "") or None,
                Year=doc.get("year"),
                Url=(
                    doc.get("landing_page_url") or doc.get("pdf_url") or doc.get("url")
                )
                or None,
                Intervention=str(intr.get("name") or "") or None,
                StudyDesign=str(intr.get("study_type") or "") or None,
                Outcome=str(res.get("outcome_variable") or "") or None,
                EffectDirection=str(res.get("effect_direction") or "") or None,
                EffectSizeType=str(res.get("effect_size_type") or "") or None,
                EffectSize=str(res.get("effect_size") or "") or None,
                PValue=str(res.get("p_value") or "") or None,
                Uncertainty=str(res.get("uncertainty") or "") or None,
                Evidence=[e for e in evidence_items if e],
            )
            all_findings.append(finding)

    # Sort similar to legacy service (desc by year, then title)
    all_findings.sort(key=lambda f: (f.Year or 0, f.SourceTitle or ""), reverse=True)
    return all_findings


def create_synthesis_workflow():
    """Create the LangGraph agent for the synthesis process.

    Starts with a single data-fetch step and terminates. Future nodes
    (e.g. clustering, self-critique, justification) will extend this.
    """
    workflow = StateGraph(SynthesisState)

    # Nodes
    workflow.add_node("fetch_project_data", fetch_project_data)
    workflow.add_node("load_raw_extractions", load_raw_extractions)
    workflow.add_node("create_canonical_concepts", create_canonical_concepts)
    workflow.add_node("fine_grained_vector_clustering", fine_grained_vector_clustering)
    workflow.add_node("label_clusters_for_themes", label_clusters_for_themes)
    workflow.add_node("build_aggregated_tables", build_aggregated_tables)
    workflow.add_node("synthesize_policy_briefing", synthesize_policy_briefing)

    # Linear flow for now
    workflow.set_entry_point("fetch_project_data")
    workflow.add_edge("fetch_project_data", "load_raw_extractions")
    workflow.add_edge("load_raw_extractions", "create_canonical_concepts")
    workflow.add_edge("create_canonical_concepts", "fine_grained_vector_clustering")
    workflow.add_edge("fine_grained_vector_clustering", "label_clusters_for_themes")
    # After labels, build tables then synthesize briefing
    workflow.add_edge("label_clusters_for_themes", "build_aggregated_tables")
    workflow.add_edge("build_aggregated_tables", "synthesize_policy_briefing")
    workflow.add_edge("synthesize_policy_briefing", END)

    return workflow.compile()


async def cluster_evidence(state: SynthesisState) -> SynthesisState:
    """Skeleton clustering node.

    For now, returns empty clusters and passes through findings. Future
    iterations will implement MECE clustering using LLM or algorithmic approaches.
    """
    print("---CLUSTERING EVIDENCE (placeholder)---")
    return {"aggregated_summary": {"issues": [], "interventions": []}}


def _cluster_labels_for_embeddings(embeddings: np.ndarray) -> np.ndarray:
    """Return cluster labels using HDBSCAN (only)."""
    if embeddings.size == 0:
        return np.array([])
    if HDBSCANLib is None:
        return np.zeros(embeddings.shape[0], dtype=int)
    try:
        # Normalise to unit length so Euclidean approximates cosine
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        unit = embeddings / norms
        n = unit.shape[0]
        # Adaptive min_cluster_size ~1% of corpus (at least 2) for finer granularity
        min_cs = max(2, int(round(0.01 * n)))
        cl = HDBSCANLib(
            min_cluster_size=min_cs,
            min_samples=1,
            metric="euclidean",
            cluster_selection_method="leaf",
        )
        return cl.fit_predict(unit)
    except Exception:
        return np.zeros(embeddings.shape[0], dtype=int)


def _assign_outliers_to_nearest(
    embeddings: np.ndarray, labels: np.ndarray, threshold: float = 0.9
) -> np.ndarray:
    """Assign -1 labels to nearest cluster centroid if similarity above threshold."""
    if embeddings.size == 0:
        return labels
    mask_noise = labels == -1
    if not np.any(mask_noise):
        return labels
    clusters = [lab for lab in np.unique(labels) if lab != -1]
    if not clusters:
        return labels
    centroids = []
    for lab in clusters:
        centroids.append(embeddings[labels == lab].mean(axis=0))
    centroids_arr = np.vstack(centroids)

    def _cos_sim(a: np.ndarray, b: np.ndarray) -> float:
        na = np.linalg.norm(a) or 1.0
        nb = np.linalg.norm(b) or 1.0
        return float(np.dot(a, b) / (na * nb))

    for idx in np.where(mask_noise)[0]:
        vec = embeddings[idx]
        sims = [_cos_sim(vec, c) for c in centroids_arr]
        best_i = int(np.argmax(sims))
        if sims[best_i] >= threshold:
            labels[idx] = clusters[best_i]
    return labels


async def fine_grained_vector_clustering(state: SynthesisState) -> SynthesisState:
    """Cluster concepts separately for issues and interventions."""
    print("---FINE-GRAINED VECTOR CLUSTERING---")
    concepts: List[Concept] = state.get("concepts", []) or []
    if not concepts:
        return {
            "issue_clusters": {},
            "intervention_clusters": {},
            "outlier_concept_ids": [],
        }

    issue_cs = [c for c in concepts if c.kind == "issue"]
    intr_cs = [c for c in concepts if c.kind == "intervention"]

    description_to_ids: Dict[str, List[str]] = state.get("description_to_ids", {}) or {}

    def _cluster(
        sub: List[Concept]
    ) -> Tuple[Dict[int, List[str]], Dict[int, List[str]], List[str]]:
        if not sub:
            return {}, {}, []
        embs = np.array([c.embedding for c in sub if c.embedding])
        if embs.size == 0:
            ids = [c.id for c in sub]
            texts = [c.canonical_description for c in sub]
            # Expand ids per description
            id_clusters = {}
            for i, desc in enumerate(texts):
                id_clusters[i] = description_to_ids.get(desc, [ids[i]])
            return id_clusters, {i: [texts[i]] for i in range(len(texts))}, []
        labels = _cluster_labels_for_embeddings(embs)
        labels = _assign_outliers_to_nearest(embs, labels)
        id_clusters: Dict[int, List[str]] = {}
        text_clusters: Dict[int, List[str]] = {}
        outliers: List[str] = []
        pos = 0
        for c in sub:
            lbl = int(labels[pos]) if pos < len(labels) else -1
            pos += 1
            if lbl == -1:
                outliers.append(c.id)
                continue
            # Expand to all extraction IDs sharing this description
            id_clusters.setdefault(lbl, []).extend(
                description_to_ids.get(c.canonical_description, [c.id])
            )
            text_clusters.setdefault(lbl, []).append(c.canonical_description)
        # De-duplicate ids within each cluster
        for k, v in list(id_clusters.items()):
            seen = set()
            uniq = []
            for eid in v:
                if eid not in seen:
                    seen.add(eid)
                    uniq.append(eid)
            id_clusters[k] = uniq
        return id_clusters, text_clusters, outliers

    issue_id_clusters, issue_text_clusters, issue_outliers = _cluster(issue_cs)
    intr_id_clusters, intr_text_clusters, intr_outliers = _cluster(intr_cs)
    outliers_all = issue_outliers + intr_outliers

    return {
        "issue_clusters": issue_text_clusters,
        "intervention_clusters": intr_text_clusters,
        "_issue_id_clusters": issue_id_clusters,
        "_intervention_id_clusters": intr_id_clusters,
        "outlier_concept_ids": outliers_all,
    }


async def label_clusters_for_themes(state: SynthesisState) -> SynthesisState:
    """Assign human-readable theme names and map extraction IDs to themes."""
    print("---LABELING CLUSTERS FOR THEMES---")
    issue_clusters = dict(state.get("issue_clusters", {}) or {})
    intr_clusters = dict(state.get("intervention_clusters", {}) or {})

    issue_theme_names: Dict[int, str] = {}
    intr_theme_names: Dict[int, str] = {}

    # Parallelise with bounded concurrency
    sem = asyncio.Semaphore(8)

    async def name_issue(cid: int, texts: List[str]) -> Tuple[int, str]:
        async with sem:
            try:
                tn = await _generate_theme_name_for_cluster(texts)
            except Exception:
                tn = f"Theme: Issue Cluster {cid}"
            return cid, tn

    async def name_intr(cid: int, texts: List[str]) -> Tuple[int, str]:
        async with sem:
            try:
                tn = await _generate_theme_name_for_cluster(texts)
            except Exception:
                tn = f"Theme: Intervention Cluster {cid}"
            return cid, tn

    issue_tasks = [name_issue(cid, texts) for cid, texts in issue_clusters.items()]
    intr_tasks = [name_intr(cid, texts) for cid, texts in intr_clusters.items()]
    for cid, tn in await asyncio.gather(*issue_tasks):
        issue_theme_names[cid] = tn
    for cid, tn in await asyncio.gather(*intr_tasks):
        intr_theme_names[cid] = tn

    # Post-process names: strip "Theme:" prefix, encourage specificity, Title Case, cap length
    def _clean(name: str) -> str:
        t = (name or "").strip()
        if t.lower().startswith("theme:"):
            t = t.split(":", 1)[1].strip()
        # Trim generic umbrella starters
        generic_prefixes = [
            "Obesity Management",
            "Weight Management",
            "Cardiovascular Health",
            "Public Health",
            "Healthcare Policy",
        ]
        for gp in generic_prefixes:
            if t.lower().startswith(gp.lower()):
                # Keep the rest if present; otherwise leave as-is
                parts = t.split("-", 1)
                if len(parts) == 2 and parts[1].strip():
                    t = parts[1].strip()
                break
        # Title Case while preserving acronyms
        t = " ".join(
            [w if w.isupper() and len(w) <= 5 else w.capitalize() for w in t.split()]
        )
        if len(t) > 72:
            t = t[:72].rstrip()
        return t

    issue_theme_names = {cid: _clean(n) for cid, n in issue_theme_names.items()}
    intr_theme_names = {cid: _clean(n) for cid, n in intr_theme_names.items()}

    issue_id_clusters: Dict[int, List[str]] = state.get("_issue_id_clusters", {}) or {}
    intr_id_clusters: Dict[int, List[str]] = (
        state.get("_intervention_id_clusters", {}) or {}
    )
    finding_to_theme_map: Dict[str, Dict[str, str]] = {}

    for cid, ids in issue_id_clusters.items():
        tname = issue_theme_names.get(cid, "")
        for ext_id in ids:
            finding_to_theme_map.setdefault(ext_id, {}).update({"issue_theme": tname})

    for cid, ids in intr_id_clusters.items():
        tname = intr_theme_names.get(cid, "")
        for ext_id in ids:
            finding_to_theme_map.setdefault(ext_id, {}).update(
                {"intervention_theme": tname}
            )

    return {
        "issue_theme_names": issue_theme_names,
        "intervention_theme_names": intr_theme_names,
        "finding_to_theme_map": finding_to_theme_map,
    }


async def critique_clusters(state: SynthesisState) -> SynthesisState:
    """Skeleton critique node.

    Adds placeholder critique notes to support later self-correction.
    """
    print("---CRITIQUE CLUSTERS (placeholder)---")
    return {"critique_notes": "No critique yet (placeholder)."}


async def build_justifications(state: SynthesisState) -> SynthesisState:
    """Skeleton justification node.

    Produces placeholder provenance/justifications for transparency.
    """
    print("---BUILD JUSTIFICATIONS (placeholder)---")
    return {"justifications": {"issues": [], "interventions": []}}


async def generate_briefing(state: SynthesisState) -> SynthesisState:
    """Skeleton executive briefing generation node.

    Uses the research question and (future) clusters to generate a briefing.
    """
    print("---GENERATE BRIEFING (placeholder)---")
    rq = state.get("research_question") or "Not specified"
    briefing = (
        "Executive briefing is being generated by the new agent. "
        f"Research question: {rq}"
    )
    return {"executive_briefing": briefing}


async def synthesize_policy_briefing(state: SynthesisState) -> SynthesisState:
    """Generate policy-grade executive briefing from aggregated tables."""
    print("---SYNTHESIZING POLICY BRIEFING---")
    research_question = state.get("research_question", "")
    ag_issues = state.get("aggregated_issues", []) or []
    ag_intrs = state.get("aggregated_interventions", []) or []
    top_issues = sorted(ag_issues, key=lambda x: x.frequency, reverse=True)[:3]
    top_interventions = sorted(ag_intrs, key=lambda x: x.frequency, reverse=True)[:3]

    structured_data_for_prompt = {
        "top_issues": [i.dict() for i in top_issues],
        "top_interventions": [t.dict() for t in top_interventions],
    }

    system = "You are a Principal Policy Advisor. Respond with a concise, neutral executive briefing."
    user = (
        "Write an evidence-grounded briefing strictly using the provided data.\n"
        "Structure: Opening sentence; Key Challenges (2-3); Recommended Interventions (2-3); Evidence Assessment.\n"
        f'Research question: "{research_question}"\n\n'
        f"Structured Evidence Data: {_escape_braces(json.dumps(structured_data_for_prompt)[:15000])}"
    )
    # Defensive fallback if no clusters available
    if not top_issues and not top_interventions:
        briefing = (
            f"For the question '{research_question}', no robust clustered themes were identified from the available extractions. "
            "The evidence base appears sparse or heterogeneous across documents. Consider re-running analysis with broader sources or adjusted filters."
        )
    else:
        prompt = ChatPromptTemplate.from_messages([("system", system), ("user", user)])
        try:
            llm = get_llm(settings.LLM_MODEL, temperature=0.2)
            resp = llm.invoke(prompt.format())
            briefing = (resp.content if hasattr(resp, "content") else str(resp)).strip()
            if briefing.startswith("```"):
                briefing = briefing.strip("`")
                if briefing.startswith("text\n"):
                    briefing = briefing[len("text\n") :]
        except Exception:
            briefing = (
                f"In response to the query on '{research_question}', the evidence points to key challenges. "
                "The recommended interventions derive from the most frequent clustered themes. "
                "The evidence base spans multiple sources."
            )

    return {"executive_briefing": briefing}


async def build_aggregated_tables(state: SynthesisState) -> SynthesisState:
    """Construct final aggregated tables with summaries and justifications.

    Uses clustered themes and document mappings to produce KeyIssue and
    PolicyIntervention lists suitable for API consumption.
    """
    print("---BUILDING AGGREGATED TABLES---")
    project_id = state.get("project_id", "")

    # Fetch documents to map theme concepts back to document IDs
    supabase = vectorization_service.supabase
    docs_res = (
        supabase.table("analysis_documents")
        .select("id, doc_id, extraction_results")
        .eq("analysis_project_id", project_id)
        .execute()
    )
    documents = docs_res.data or []

    # Robust mapping: use finding_to_theme_map (extraction_id -> theme names) to compute doc_id sets per theme
    finding_to_theme_map: Dict[str, Dict[str, str]] = (
        state.get("finding_to_theme_map", {}) or {}
    )
    # Fetch extraction rows to map extraction_id -> analysis_document_id -> doc_id
    ex_ids = list(finding_to_theme_map.keys())
    extraction_to_doc_id: Dict[str, str] = {}
    if ex_ids:
        # Supabase doesn't support IN with huge lists in a single call in all clients; chunk if needed
        CHUNK = 1000
        for i in range(0, len(ex_ids), CHUNK):
            chunk = ex_ids[i : i + CHUNK]
            exts_res = (
                supabase.table("analysis_extractions")
                .select("id, analysis_document_id")
                .in_("id", chunk)
                .execute()
            )
            rows = exts_res.data or []
            # Map analysis_document_id -> doc_id from previously fetched documents
            doc_uuid_to_doc_id = {
                str(d.get("id")): str(d.get("doc_id") or "") for d in documents
            }
            for r in rows:
                rid = str(r.get("id"))
                doc_uuid = str(r.get("analysis_document_id") or "")
                extraction_to_doc_id[rid] = doc_uuid_to_doc_id.get(doc_uuid, "")

    # Aggregate doc_ids per theme using assignments
    issue_theme_to_doc_ids: Dict[str, set] = {}
    intr_theme_to_doc_ids: Dict[str, set] = {}
    for ex_id, mapping in finding_to_theme_map.items():
        did = extraction_to_doc_id.get(ex_id, "")
        if not did:
            continue
        it = mapping.get("issue_theme")
        kt = mapping.get("intervention_theme")
        if it:
            issue_theme_to_doc_ids.setdefault(it, set()).add(did)
        if kt:
            intr_theme_to_doc_ids.setdefault(kt, set()).add(did)

    aggregated_issues: List[KeyIssue] = []
    aggregated_interventions: List[PolicyIntervention] = []

    # Summarise issues
    issue_clusters = state.get("issue_clusters", {}) or {}
    issue_theme_names = state.get("issue_theme_names", {}) or {}

    # Parallelise summaries for issues (only for larger themes)
    async def summarise_issue(
        cid: int, theme_name: str, concept_texts: List[str], doc_ids: List[str]
    ) -> KeyIssue:
        frequency = len(doc_ids) or len(concept_texts)
        try:
            summary = await _generate_theme_summary(theme_name, concept_texts)
        except Exception:
            summary = (
                f"Summary for {theme_name} based on {len(concept_texts)} concept(s)."
            )

        justification = f"Grouped {len(concept_texts)} related concept(s) under a standardised theme."
        return KeyIssue(
            issue_theme=theme_name,
            summary_description=summary,
            frequency=frequency,
            source_doc_ids=doc_ids,
            justification=justification,
        )

    # Summarise interventions
    intr_clusters = state.get("intervention_clusters", {}) or {}
    intr_theme_names = state.get("intervention_theme_names", {}) or {}

    async def summarise_intervention(
        cid: int, theme_name: str, concept_texts: List[str], doc_ids: List[str]
    ) -> PolicyIntervention:
        frequency = len(doc_ids) or len(concept_texts)
        try:
            brief_description = await _generate_intervention_brief(
                theme_name, concept_texts
            )
        except Exception:
            brief_description = (
                f"Brief description for {theme_name} derived from clustered concepts."
            )
        try:
            impact_summary = await _generate_intervention_impact(
                theme_name, concept_texts
            )
        except Exception:
            impact_summary = (
                "Synthesised impact across documents based on the clustered concepts."
            )
        justification = f"Grouped {len(concept_texts)} related concept(s) under a standardised theme."
        return PolicyIntervention(
            intervention_name=theme_name,
            brief_description=brief_description,
            impact_summary=impact_summary,
            frequency=frequency,
            supporting_doc_ids=doc_ids,
            justification=justification,
        )

    # Build task lists
    issue_tasks = []
    for cid, concept_texts in issue_clusters.items():
        theme_name = issue_theme_names.get(cid) or "Issue Theme"
        doc_ids = sorted(list(issue_theme_to_doc_ids.get(theme_name, set())))
        issue_tasks.append(summarise_issue(cid, theme_name, concept_texts, doc_ids))
    intr_tasks = []
    for cid, concept_texts in intr_clusters.items():
        theme_name = intr_theme_names.get(cid) or "Intervention Theme"
        doc_ids = sorted(list(intr_theme_to_doc_ids.get(theme_name, set())))
        intr_tasks.append(
            summarise_intervention(cid, theme_name, concept_texts, doc_ids)
        )

    # Run in parallel with bounded semaphore
    sem = asyncio.Semaphore(8)

    async def _guard(coro):
        async with sem:
            return await coro

    aggregated_issues = (
        await asyncio.gather(*[_guard(t) for t in issue_tasks]) if issue_tasks else []
    )
    aggregated_interventions = (
        await asyncio.gather(*[_guard(t) for t in intr_tasks]) if intr_tasks else []
    )

    return {
        "aggregated_issues": aggregated_issues,
        "aggregated_interventions": aggregated_interventions,
    }


def _apply_theme_suggestions(state: SynthesisState, suggestions: Dict) -> None:
    """Apply merges, renames and moves to in-memory clusters and names.

    Mutates the provided state dict in-place. Assumes cluster IDs are current
    integer keys; re-indexes as needed on merges.
    """
    issue_clusters: Dict[int, List[str]] = dict(state.get("issue_clusters", {}) or {})
    intr_clusters: Dict[int, List[str]] = dict(
        state.get("intervention_clusters", {}) or {}
    )
    issue_names: Dict[int, str] = dict(state.get("issue_theme_names", {}) or {})
    intr_names: Dict[int, str] = dict(state.get("intervention_theme_names", {}) or {})

    def _merge(ids: List[int], to_name: str, is_issue: bool) -> None:
        clusters = issue_clusters if is_issue else intr_clusters
        names = issue_names if is_issue else intr_names
        # Create new cluster id
        new_id = max(clusters.keys() or [-1]) + 1
        merged: List[str] = []
        for cid in ids:
            merged.extend(clusters.get(int(cid), []))
            clusters.pop(int(cid), None)
            names.pop(int(cid), None)
        # De-duplicate while preserving order
        seen = set()
        merged_unique = []
        for t in merged:
            if t not in seen:
                seen.add(t)
                merged_unique.append(t)
        clusters[new_id] = merged_unique
        names[new_id] = to_name

    def _rename(cid: int, to_name: str, is_issue: bool) -> None:
        names = issue_names if is_issue else intr_names
        if int(cid) in names:
            names[int(cid)] = to_name

    def _move(concept: str, src: int, dst: int, is_issue: bool) -> None:
        clusters = issue_clusters if is_issue else intr_clusters
        src_list = clusters.get(int(src), [])
        dst_list = clusters.setdefault(int(dst), [])
        if concept in src_list:
            src_list = [t for t in src_list if t != concept]
            clusters[int(src)] = src_list
            if concept not in dst_list:
                dst_list.append(concept)

    # Apply merges
    for m in suggestions.get("merges", []) or []:
        declared_issue = (m.get("type") or "").lower().startswith("issue")

        from_val = m.get("from")
        to_val = m.get("to")
        to_name = m.get("to_name") or m.get("new_name")

        if from_val is not None and to_val is not None:
            # Try integer IDs first
            handled = False
            try:
                from_id, to_id = int(from_val), int(to_val)
                # If type declared, act on that set. Otherwise infer based on id presence.
                candidate_sets = []
                if declared_issue:
                    candidate_sets = [(issue_clusters, issue_names)]
                elif (from_id in issue_clusters or to_id in issue_clusters) and (
                    from_id not in intr_clusters and to_id not in intr_clusters
                ):
                    candidate_sets = [(issue_clusters, issue_names)]
                elif (from_id in intr_clusters or to_id in intr_clusters) and (
                    from_id not in issue_clusters and to_id not in issue_clusters
                ):
                    candidate_sets = [(intr_clusters, intr_names)]
                else:
                    candidate_sets = [
                        (issue_clusters, issue_names),
                        (intr_clusters, intr_names),
                    ]

                for clusters, names in candidate_sets:
                    if from_id in clusters and to_id in clusters:
                        source_concepts = clusters[from_id]
                        target_concepts = clusters[to_id]
                    merged_concepts = target_concepts[:]
                    for concept in source_concepts:
                        if concept not in merged_concepts:
                            merged_concepts.append(concept)
                        clusters[to_id] = merged_concepts
                        del clusters[from_id]
                        if from_id in names:
                            del names[from_id]
                        if to_name:
                            names[to_id] = str(to_name).strip()
                            handled = True
                if handled:
                    continue
            except ValueError:
                pass

            # Fallback: handle as theme names across both sets
            from_theme = str(from_val).strip()
            to_theme = str(to_val).strip()
            for clusters, names in (
                (issue_clusters, issue_names),
                (intr_clusters, intr_names),
            ):
                from_id = None
                to_id = None
                for cid, theme_name in names.items():
                    if theme_name == from_theme:
                        from_id = cid
                    elif theme_name == to_theme:
                        to_id = cid
                if from_id is not None and to_id is not None:
                    source_concepts = clusters.get(from_id, [])
                    target_concepts = clusters.get(to_id, [])
                    merged_concepts = target_concepts[:]
                    for concept in source_concepts:
                        if concept not in merged_concepts:
                            merged_concepts.append(concept)
                    clusters[to_id] = merged_concepts
                    if from_id in clusters:
                        del clusters[from_id]
                    if from_id in names:
                        del names[from_id]
                    if to_name:
                        names[to_id] = str(to_name).strip()

        # Fallback: handle legacy format with "from" as array and "to_name"
        elif m.get("from") and m.get("to_name"):
            from_val = m.get("from")
            if isinstance(from_val, list):
                ids = []
                for x in from_val:
                    try:
                        ids.append(int(str(x).split(".")[-1]))
                    except Exception:
                        continue
            elif from_val is not None:
                try:
                    ids = [int(str(from_val).split(".")[-1])]
                except Exception:
                    ids = []
            else:
                ids = []

            to_name = str(m.get("to_name") or "Merged Theme").strip()
            if ids:
                # Attempt merge in both spaces if type not explicit
                if declared_issue:
                    _merge(ids, to_name, True)
                else:
                    try:
                        _merge(ids, to_name, True)
                    except Exception:
                        pass
                    try:
                        _merge(ids, to_name, False)
                    except Exception:
                        pass

    # Apply renames
    for r in suggestions.get("renames", []) or []:
        declared_issue = (r.get("type") or "").lower().startswith("issue")

        old_name = r.get("old")
        new_name = r.get("new") or r.get("new_name") or r.get("to_name")
        cid = r.get("id") or r.get("index")

        if old_name and new_name:
            targets = []
            if declared_issue:
                targets = [(issue_clusters, issue_names)]
            else:
                targets = [
                    (issue_clusters, issue_names),
                    (intr_clusters, intr_names),
                ]
            for _, names in targets:
                target_cid = None
                for cluster_id, theme_name in names.items():
                    if theme_name == str(old_name).strip():
                        target_cid = cluster_id
                        break
                if target_cid is not None:
                    names[target_cid] = str(new_name).strip()
        elif cid is not None:
            try:
                cid_int = int(cid)
            except ValueError:
                cid_int = None
            if cid_int is not None:
                to_name = str(new_name or "Theme").strip()
                if declared_issue or cid_int in issue_names:
                    _rename(cid_int, to_name, True)
                if (not declared_issue) or cid_int in intr_names:
                    _rename(cid_int, to_name, False)

    # Apply moves
    for mv in suggestions.get("moves", []) or []:
        concept = str(mv.get("concept") or "").strip()
        src_raw = mv.get("from")
        dst_raw = mv.get("to")
        try:
            src = int(src_raw) if src_raw is not None else None
            dst = int(dst_raw) if dst_raw is not None else None
        except ValueError:
            src, dst = None, None
        if concept and src is not None and dst is not None:
            # Try both sets if type not specified
            tflag = (mv.get("type") or "").lower().startswith("issue")
            if tflag or (src in issue_clusters or dst in issue_clusters):
                _move(concept, src, dst, True)
            if (not tflag) or (src in intr_clusters or dst in intr_clusters):
                _move(concept, src, dst, False)

    # Write back
    state["issue_clusters"] = issue_clusters
    state["intervention_clusters"] = intr_clusters
    state["issue_theme_names"] = issue_names
    state["intervention_theme_names"] = intr_names


def _escape_braces(text: str) -> str:
    """Escape braces for ChatPromptTemplate formatting."""
    return (text or "").replace("{", "{{").replace("}", "}}")


def _get_concepts_from_findings(
    findings: List[Finding], concept_type: str
) -> List[Tuple[str, str]]:
    """Extract concepts (issues or interventions) from raw findings.

    Note: current Finding schema lacks an Issue field; we only extract interventions
    for now and leave issues empty until issue extraction is available.
    """
    concepts: List[Tuple[str, str]] = []
    for f in findings:
        if concept_type == "intervention" and (f.Intervention or "").strip():
            concepts.append((f.DocId or f.SourceTitle, str(f.Intervention)))
        elif concept_type == "issue":
            # Placeholder: no issue field in Finding schema yet
            pass
    return concepts


async def _cluster_and_theme_concepts(
    concepts: List[Tuple[str, str]],  # (extraction_id, concept_text)
) -> Tuple[Dict[int, List[str]], Dict[str, str]]:
    """LLM-based semantic clustering for short concept texts.

    Returns: (clusters, concept_to_theme_name_mapping)
    - clusters: {cluster_id: [concept_texts]}
    - mapping: {concept_text: theme_name}
    """
    if not concepts:
        return {}, {}

    concept_texts = [text for _, text in concepts]

    print(f"LLM clustering {len(concept_texts)} concepts")

    try:
        # Use LLM to semantically group concepts
        from langchain_core.prompts import ChatPromptTemplate
        from app.core.config import settings

        llm = get_llm(settings.LLM_MODEL, temperature=0.1)

        # Prepare concepts list for the prompt
        concepts_list = "\n".join(
            [f"{i+1}. {text}" for i, text in enumerate(concept_texts)]
        )

        print(f"Debug - LLM clustering input: {concepts_list[:200]}...")

        prompt = ChatPromptTemplate.from_template(
            """
You are an expert policy researcher tasked with grouping related concepts into coherent themes.

Review the following list of concepts and group them into 3-8 meaningful themes based on semantic similarity and policy relevance. Concepts that are very similar should be grouped together, while distinct concepts should remain separate.

CONCEPTS TO GROUP:
{concepts_list}

Provide your response as a JSON object with this structure:
{{"groups": [
  {{
    "theme_name": "Clear, descriptive theme name", 
    "concepts": ["concept 1", "concept 2", "concept 3"],
    "rationale": "Brief explanation of why these concepts belong together"
  }}
]}}

Guidelines:
- Aim for 3-8 groups total (fewer groups with more concepts each)
- Group names should be clear and descriptive  
- Each concept should appear in exactly one group
- If a concept is truly unique, it can form its own group
- Focus on semantic meaning and policy domain, not just keyword matching
- Prioritize creating meaningful larger groups over many small groups
"""
        )

        formatted_prompt = prompt.format(concepts_list=_escape_braces(concepts_list))
        print("Debug - About to call LLM for clustering")
        response = await llm.ainvoke(formatted_prompt)
        print(f"Debug - LLM clustering response type: {type(response)}")

        # Parse LLM response
        content = response.content.strip()
        print(f"Debug - LLM clustering raw content: {content[:500]}...")

        if content.startswith("```json"):
            content = content[7:-3]
        elif content.startswith("```"):
            content = content[3:-3]

        print(f"Debug - Cleaned content for JSON parsing: {content[:200]}...")

        import json

        groups_data = json.loads(content)
        groups_list = groups_data.get("groups", [])
        print(f"Debug - Successfully parsed JSON with {len(groups_list)} groups")

        if not groups_list:
            print(
                "Debug - LLM returned empty groups list, falling back to individual clusters"
            )
            raise ValueError("LLM returned empty groups")

        # Convert to our cluster format
        clusters: Dict[int, List[str]] = {}
        concept_to_theme_name: Dict[str, str] = {}

        for cluster_id, group in enumerate(groups_list):
            theme_name = group.get("theme_name", f"Theme {cluster_id + 1}")
            concepts_in_group = group.get("concepts", [])

            print(
                f"Debug - Processing group {cluster_id}: '{theme_name}' with {len(concepts_in_group)} concepts"
            )

            if concepts_in_group:
                clusters[cluster_id] = concepts_in_group
                for concept in concepts_in_group:
                    concept_to_theme_name[concept] = theme_name

        # Handle any concepts that weren't grouped by the LLM
        grouped_concepts = set(concept_to_theme_name.keys())
        ungrouped = [c for c in concept_texts if c not in grouped_concepts]

        if ungrouped:
            print(
                f"Debug - {len(ungrouped)} concepts were not grouped by LLM: {ungrouped[:5]}..."
            )

        next_id = len(clusters)
        for concept in ungrouped:
            clusters[next_id] = [concept]
            concept_to_theme_name[concept] = f"Theme: {concept}"
            next_id += 1

        print(f"LLM created {len(clusters)} semantic clusters:")
        for cid, concepts_in_cluster in clusters.items():
            theme_name = concept_to_theme_name.get(
                concepts_in_cluster[0], f"Theme {cid}"
            )
            print(f"  {theme_name}: {len(concepts_in_cluster)} concepts")

        return clusters, concept_to_theme_name

    except Exception as e:
        print(f"LLM clustering failed with error: {type(e).__name__}: {e}")
        import traceback

        print(f"LLM clustering traceback: {traceback.format_exc()}")
    # Fallback: each concept gets its own cluster
    clusters = {i: [text] for i, text in enumerate(concept_texts)}
    concept_to_theme_name = {text: f"Theme: {text}" for text in concept_texts}
    print(f"Falling back to {len(clusters)} individual clusters")
    return clusters, concept_to_theme_name


async def _generate_theme_name_for_cluster(concept_texts: List[str]) -> str:
    """Generate a concise theme name for a cluster of related concepts using LLM."""
    from app.utils.llm.llm_utils import get_llm
    from app.core.config import settings

    # Nudge towards specificity by showing a few most distinctive tokens first
    concepts_str = "\n".join(f"- {text}" for text in concept_texts[:10])

    system = "You generate concise, specific theme names for clusters of related concepts. Avoid broad umbrella categories. Do NOT use words like Obesity, Management, Comprehensive, Strategy/Strategies."
    user = f"""Create a short, specific theme name (3–6 words) capturing the most distinctive commonality across these concepts. Avoid umbrellas (e.g., 'Obesity Management'); name the precise issue or lever (e.g., prior authorisation, school breakfast, sugar tax, GLP‑1 eligibility).

{concepts_str}

Return ONLY the theme name, starting with "Theme: "."""

    prompt = ChatPromptTemplate.from_messages([("system", system), ("user", user)])
    llm = get_llm(settings.LLM_MODEL, temperature=0.0)
    resp = await llm.ainvoke(prompt.format())
    theme_name = (resp.content if hasattr(resp, "content") else str(resp)).strip()

    # Ensure it starts with "Theme: "
    if not theme_name.startswith("Theme: "):
        theme_name = f"Theme: {theme_name}"

    return theme_name


async def _generate_theme_summary(theme_name: str, concept_texts: List[str]) -> str:
    """Generate a descriptive summary for a theme based on its concepts."""
    from app.utils.llm.llm_utils import get_llm
    from app.core.config import settings

    concepts_str = "\n".join(f"- {text}" for text in concept_texts[:10])

    system = "You are a policy researcher writing succinct, neutral UK policy brief lines. Be specific; do NOT write umbrellas (avoid: Obesity, Management, Comprehensive, Strategy)."
    user = f"""Write a 35–45 word, 1–2 sentence summary for this precise theme; end with one policy action.

Theme: {theme_name}
Related concepts: {concepts_str}

Requirements: British English; no markdown; avoid filler; avoid hedging; be specific and actionable."""

    prompt = ChatPromptTemplate.from_messages([("system", system), ("user", user)])
    llm = get_llm(settings.LLM_MODEL, temperature=0.1)
    resp = await llm.ainvoke(prompt.format())
    return (resp.content if hasattr(resp, "content") else str(resp)).strip()


async def _generate_intervention_brief(
    theme_name: str, concept_texts: List[str]
) -> str:
    """Generate a brief description for an intervention theme."""
    from app.utils.llm.llm_utils import get_llm
    from app.core.config import settings

    concepts_str = "\n".join(f"- {text}" for text in concept_texts[:10])

    system = "You write succinct, neutral UK policy brief lines. Describe the concrete lever; avoid umbrellas (avoid: Obesity, Management, Comprehensive, Strategy)."
    user = f"""Write a 35–45 word, 1–2 sentence brief; end with one policy action. Be specific to this lever.

Theme: {theme_name}
Related interventions: {concepts_str}

State what they do and the common approach; British English; no markdown."""

    prompt = ChatPromptTemplate.from_messages([("system", system), ("user", user)])
    llm = get_llm(settings.LLM_MODEL, temperature=0.1)
    resp = await llm.ainvoke(prompt.format())
    return (resp.content if hasattr(resp, "content") else str(resp)).strip()


async def _generate_intervention_impact(
    theme_name: str, concept_texts: List[str]
) -> str:
    """Generate an impact summary for an intervention theme."""
    from app.utils.llm.llm_utils import get_llm
    from app.core.config import settings

    concepts_str = "\n".join(f"- {text}" for text in concept_texts)

    system = "You write succinct, neutral UK policy impact lines."
    user = f"""Write a 35–45 word, 1–2 sentence impact summary; end with one policy action.

Theme: {theme_name}
Related interventions: {concepts_str}

Describe expected impacts and effectiveness; British English; focus on outcomes; no markdown."""

    prompt = ChatPromptTemplate.from_messages([("system", system), ("user", user)])
    llm = get_llm(settings.LLM_MODEL, temperature=0.1)
    resp = await llm.ainvoke(prompt.format())
    return (resp.content if hasattr(resp, "content") else str(resp)).strip()


async def generate_and_assign_themes(state: SynthesisState) -> SynthesisState:
    """Generate MECE themes for issues and interventions from raw findings."""
    print("---GENERATING & ASSIGNING THEMES---")
    project_id = state.get("project_id", "")

    # Check if this is a re-iteration (themes already exist and have been modified)
    current_iteration = state.get("theme_iteration", 0)
    if (
        current_iteration > 0
        and state.get("issue_clusters")
        and state.get("intervention_clusters")
    ):
        print(f"Re-iteration {current_iteration}: preserving existing clusters")
        # Return existing state without re-clustering
        return state

    print("Initial clustering: generating themes from raw extractions")
    issue_concepts = _get_issue_concepts_for_project(project_id)
    intr_concepts = _get_intervention_concepts_for_project(project_id)

    # Build helper maps: concept text -> set(extraction_ids)
    issue_text_to_ext_ids: Dict[str, set] = {}
    extraction_text_by_id: Dict[str, str] = {}
    for ext_id, text in issue_concepts:
        extraction_text_by_id[ext_id] = text
        issue_text_to_ext_ids.setdefault(text, set()).add(ext_id)
    intr_text_to_ext_ids: Dict[str, set] = {}
    for ext_id, text in intr_concepts:
        extraction_text_by_id[ext_id] = text
        intr_text_to_ext_ids.setdefault(text, set()).add(ext_id)

    issue_clusters_raw, issue_map = await _cluster_and_theme_concepts(issue_concepts)
    intr_clusters_raw, intr_map = await _cluster_and_theme_concepts(intr_concepts)

    # Use the actual clustering results directly
    issue_clusters = issue_clusters_raw
    intr_clusters = intr_clusters_raw

    # Create theme name mappings
    issue_theme_names = {}
    intervention_theme_names = {}

    # Get theme names for each cluster
    for cluster_id, concept_texts in issue_clusters.items():
        # Get theme name for any concept in this cluster (they all have the same theme)
        theme_name = issue_map.get(
            concept_texts[0], f"Theme: Issue Cluster {cluster_id}"
        )
        issue_theme_names[cluster_id] = theme_name

    for cluster_id, concept_texts in intr_clusters.items():
        # Get theme name for any concept in this cluster (they all have the same theme)
        theme_name = intr_map.get(
            concept_texts[0], f"Theme: Intervention Cluster {cluster_id}"
        )
        intervention_theme_names[cluster_id] = theme_name

    # Build finding-to-theme mapping using extraction IDs
    finding_to_theme_map: Dict[str, Dict[str, str]] = {}
    # Issue assignments
    for cid, concepts in issue_clusters.items():
        theme_name = issue_theme_names.get(cid, "")
        for concept_text in concepts:
            for ext_id in issue_text_to_ext_ids.get(concept_text, set()):
                finding_to_theme_map.setdefault(ext_id, {}).update(
                    {"issue_theme": theme_name}
                )
    # Intervention assignments
    for cid, concepts in intr_clusters.items():
        theme_name = intervention_theme_names.get(cid, "")
        for concept_text in concepts:
            for ext_id in intr_text_to_ext_ids.get(concept_text, set()):
                finding_to_theme_map.setdefault(ext_id, {}).update(
                    {"intervention_theme": theme_name}
                )

    return {
        **state,
        "issue_clusters": issue_clusters,
        "intervention_clusters": intr_clusters,
        "issue_theme_names": issue_theme_names,
        "intervention_theme_names": intervention_theme_names,
        "finding_to_theme_map": finding_to_theme_map,
        "extraction_text_by_id": extraction_text_by_id,
    }


def _get_issue_concepts_for_project(project_id: str) -> List[Tuple[str, str]]:
    """Extract issue concepts from analysis_extractions as (extraction_id, text).

    De-duplicates per analysis_document_id + normalised text while retaining a
    representative extraction_id for each unique concept per document.
    """
    if not project_id:
        return []
    supabase = vectorization_service.supabase
    exts_res = (
        supabase.table("analysis_extractions")
        .select("id, analysis_document_id, extraction_type, label, raw_data")
        .eq("analysis_project_id", project_id)
        .eq("extraction_type", "issue")
        .execute()
    )
    rows = exts_res.data or []
    # De-duplicate per document
    seen: Dict[Tuple[str, str], str] = {}
    for row in rows:
        doc_uuid = str(row.get("analysis_document_id") or "")
        label = str(
            row.get("label") or (row.get("raw_data") or {}).get("label") or ""
        ).strip()
        if not label:
            continue
        key = (doc_uuid, _normalise_concept(label))
        if key not in seen:
            seen[key] = str(row.get("id"))
    concepts: List[Tuple[str, str]] = [
        (ext_id, label) for (_, norm), ext_id in seen.items() for label in [norm]
    ]
    return concepts


def _get_intervention_concepts_for_project(project_id: str) -> List[Tuple[str, str]]:
    """Extract intervention concepts from analysis_extractions as (extraction_id, text).

    De-duplicates per analysis_document_id + normalised text while retaining a
    representative extraction_id for each unique concept per document.
    """
    if not project_id:
        return []
    supabase = vectorization_service.supabase
    exts_res = (
        supabase.table("analysis_extractions")
        .select("id, analysis_document_id, extraction_type, label, raw_data")
        .eq("analysis_project_id", project_id)
        .eq("extraction_type", "intervention")
        .execute()
    )
    rows = exts_res.data or []
    seen: Dict[Tuple[str, str], str] = {}
    for row in rows:
        doc_uuid = str(row.get("analysis_document_id") or "")
        name = str(
            row.get("label") or (row.get("raw_data") or {}).get("name") or ""
        ).strip()
        if not name:
            continue
        key = (doc_uuid, _normalise_concept(name))
        if key not in seen:
            seen[key] = str(row.get("id"))
    concepts: List[Tuple[str, str]] = [
        (ext_id, label) for (_, label), ext_id in seen.items()
    ]
    return concepts


def _normalise_concept(text: str) -> str:
    """Normalise concept text for de-duplication.

    Lowercase, trim, and collapse internal whitespace. Keep punctuation to
    avoid over-merging distinct concepts; further canonicalisation can be
    added later if needed.
    """
    t = (text or "").strip().lower()
    t = " ".join(t.split())
    return t


async def critique_generated_themes(state: SynthesisState) -> SynthesisState:
    """Evaluate generated themes for MECE quality using LLM; return JSON suggestions.

    Expected LLM output (JSON):
    {
      "merges": [ {"type": "issue|intervention", "from": [cluster_ids...], "to_name": "New Canonical Name"}, ...],
      "renames": [ {"type": "issue|intervention", "id": cluster_id, "to_name": "Better Name"}, ...],
      "moves": [ {"type": "issue|intervention", "concept": "text", "from": cluster_id, "to": cluster_id}, ...]
    }
    Return None if themes appear MECE.
    """
    print("---CRITIQUING GENERATED THEMES---")
    print(f"Debug - Starting critique with state keys: {list(state.keys())}")
    print(f"Debug - Issue clusters: {state.get('issue_clusters', {})}")
    print(f"Debug - Intervention clusters: {state.get('intervention_clusters', {})}")

    issues = {
        str(cid): {
            "name": state.get("issue_theme_names", {}).get(cid, ""),
            "concepts": state.get("issue_clusters", {}).get(cid, []),
        }
        for cid in (state.get("issue_clusters", {}) or {}).keys()
    }
    intrs = {
        str(cid): {
            "name": state.get("intervention_theme_names", {}).get(cid, ""),
            "concepts": state.get("intervention_clusters", {}).get(cid, []),
        }
        for cid in (state.get("intervention_clusters", {}) or {}).keys()
    }

    payload = {"issues": issues, "interventions": intrs}
    system = "You critique thematic clusters for MECE quality. Respond with STRICT JSON only."
    user = (
        "Review the clusters. Identify overlaps, poor names, miscategorized concepts.\n"
        'If acceptable MECE, respond with: {{"merges":[],"renames":[],"moves":[]}}\n\n'
        f"Clusters: {_escape_braces(json.dumps(payload)[:15000])}"
    )
    prompt = ChatPromptTemplate.from_messages([("system", system), ("user", user)])
    llm = get_llm(settings.LLM_MODEL, temperature=0.0)

    print("Debug - About to call LLM with prompt")
    try:
        resp = llm.invoke(prompt.format())
        print(f"Debug - LLM call successful, response type: {type(resp)}")
        text = (resp.content if hasattr(resp, "content") else str(resp)).strip()
        print(f"LLM critique raw response: {text}")  # Debug logging
    except Exception as e:
        print(f"Debug - LLM call failed: {e}")
        raise

    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json\n"):
            text = text[len("json\n") :]

    print(f"LLM critique cleaned text: {text}")  # Debug logging

    try:
        parsed = json.loads(text)
    except Exception as e:
        print(f"JSON parse error: {e}, text was: {text}")  # Debug logging
        parsed = {"merges": [], "renames": [], "moves": []}

    # Normalise out no-op actions: remove merges where from == to
    merges = []
    for m in parsed.get("merges", []) or []:
        fv = str(m.get("from") or "").strip()
        tv = str(m.get("to") or "").strip()
        if not fv or not tv:
            continue
        # Accept prefixes like issues.12 or interventions.5
        fv_norm = fv.split(".")[-1]
        tv_norm = tv.split(".")[-1]
        if fv_norm == tv_norm:
            continue
        merges.append(m)
    renames = parsed.get("renames", []) or []
    moves = parsed.get("moves", []) or []

    if not (merges or renames or moves):
        return {"theme_critique": None}

    cleaned = {"merges": merges, "renames": renames, "moves": moves}
    return {"theme_critique": json.dumps(cleaned)}

    return {"theme_critique": json.dumps(parsed)}


async def apply_critique_suggestions(state: SynthesisState) -> SynthesisState:
    """Apply critique suggestions and increment iteration counter."""
    print("---APPLYING CRITIQUE SUGGESTIONS---")
    critique_content = state.get("theme_critique")

    delta: SynthesisState = {}

    if critique_content:
        try:
            suggestions = json.loads(critique_content or "{}")
        except Exception as e:
            print(f"Debug - JSON parse error: {e}")
            suggestions = {"merges": [], "renames": [], "moves": []}

        # Snapshot before
        before_issues = json.dumps(state.get("issue_clusters", {}), sort_keys=True)
        before_intrs = json.dumps(
            state.get("intervention_clusters", {}), sort_keys=True
        )

        _apply_theme_suggestions(state, suggestions)

        # Snapshot after
        after_issues = json.dumps(state.get("issue_clusters", {}), sort_keys=True)
        after_intrs = json.dumps(state.get("intervention_clusters", {}), sort_keys=True)

        current_iter = int(state.get("theme_iteration") or 0)
        next_iter = current_iter + 1
        delta["theme_iteration"] = next_iter
        # Ensure mutated cluster keys are emitted as deltas
        delta["issue_clusters"] = state.get("issue_clusters", {})
        delta["intervention_clusters"] = state.get("intervention_clusters", {})

        # Convergence detection: if no change, clear critique to break loop
        if before_issues == after_issues and before_intrs == after_intrs:
            print("No-op critique detected; clearing critique to proceed.")
            delta["theme_critique"] = None
        print(f"Applied suggestions. Next iteration: {next_iter}")

    return delta


def check_critique(state: SynthesisState) -> str:
    """Conditional router: loop if critique exists, else proceed to next."""
    print("---CHECKING CRITIQUE---")
    critique_content = state.get("theme_critique")
    current_iter = int(state.get("theme_iteration") or 0)

    if critique_content and current_iter < 3:
        print("Critique found. Will apply suggestions and loop back.")
        return "apply_critique_suggestions"
    elif current_iter >= 3:
        print("Critique iterations maxed (3). Proceeding.")
        return "build_aggregated_tables"
    else:
        print("No critique. Proceeding.")
        return "build_aggregated_tables"


class SynthesisAgent:
    """Facade for running the synthesis workflow for a given project."""

    def __init__(self) -> None:
        self.workflow = create_synthesis_workflow()

    async def run(self, project_id: str) -> SynthesisState:
        """Run the synthesis agent and return the final state."""
        initial_state: SynthesisState = {"project_id": project_id}
        final_state: SynthesisState = await self.workflow.ainvoke(initial_state)
        return final_state
