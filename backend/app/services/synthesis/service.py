from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import List, Optional

from app.core.config import settings
from app.services.vectorization import vectorization_service
from discovery_utils.utils.llm.llm_utils import get_llm
from langchain_core.prompts import ChatPromptTemplate

from .schemas import (
    KeyIssue,
    PolicyIntervention,
    SynthesisSummary,
    Finding,
)


logger = logging.getLogger(__name__)


class SynthesisService:
    """Service that synthesises analysis outputs into a summary payload.

    Provides two high-level operations:
    - summarise: Build key issues, interventions and executive briefing
    - get_findings: Flatten detailed findings for a given filter
    """

    def __init__(self):
        self.supabase = vectorization_service.supabase

    async def summarise(self, project_id: str) -> SynthesisSummary:
        """Aggregate extraction results into key issues, interventions and briefing.

        Args:
            project_id: Analysis project identifier.

        Returns:
            SynthesisSummary: Executive briefing and aggregated tables.
        """
        # Load project
        project_res = (
            self.supabase.table("analysis_projects")
            .select("*")
            .eq("id", project_id)
            .execute()
        )
        if not project_res.data:
            raise ValueError("Project not found")

        project = project_res.data[0]
        research_question = project.get("query") or "Not specified"

        # Load documents
        docs_res = (
            self.supabase.table("analysis_documents")
            .select("*")
            .eq("analysis_project_id", project_id)
            .execute()
        )
        documents = docs_res.data or []

        def _safe_str(x: Optional[object]) -> str:
            return "" if x is None else str(x)

        # Map for fallback from analysis_extractions
        doc_uuid_to_doc_id = {
            _safe_str(d.get("id")): _safe_str(d.get("doc_id")) for d in documents
        }

        try:
            exts_res = (
                self.supabase.table("analysis_extractions")
                .select("*")
                .eq("analysis_project_id", project_id)
                .execute()
            )
            extractions = exts_res.data or []
        except Exception as e:
            logger.warning("[synthesis] Failed to read analysis_extractions: %s", e)
            extractions = []

        ext_issues_mentions: List[dict] = []
        ext_interventions_mentions: List[dict] = []
        ext_issues_by_doc: dict[str, set] = {}
        ext_interventions_by_doc: dict[str, set] = {}
        for row in extractions:
            etype = _safe_str(row.get("extraction_type"))
            doc_uuid = _safe_str(row.get("analysis_document_id"))
            doc_id = doc_uuid_to_doc_id.get(doc_uuid, "")
            raw = row.get("raw_data") or {}
            if etype == "issue":
                label = _safe_str(row.get("label") or raw.get("label"))
                if not label:
                    continue
                desc = _safe_str(
                    row.get("description")
                    or raw.get("explanation")
                    or raw.get("description")
                )
                ext_issues_mentions.append(
                    {
                        "analysis_document_id": doc_uuid,
                        "doc_id": doc_id,
                        "label": label,
                        "explanation": desc,
                    }
                )
                ext_issues_by_doc.setdefault(doc_uuid, set()).add(label)
            elif etype == "intervention":
                name = _safe_str(row.get("label") or raw.get("name"))
                if not name:
                    continue
                desc = _safe_str(row.get("description") or raw.get("description"))
                ext_interventions_mentions.append(
                    {
                        "analysis_document_id": doc_uuid,
                        "doc_id": doc_id,
                        "name": name,
                        "description": desc,
                    }
                )
                ext_interventions_by_doc.setdefault(doc_uuid, set()).add(name)

        # Build payload from documents (fallback to extraction rows if empty)
        input_payload: List[dict] = []
        num_issues_seen = 0
        num_interventions_seen = 0
        has_any_doc_issues = False
        has_any_doc_interventions = False
        for doc in documents:
            extraction_results = doc.get("extraction_results") or {}
            issues = extraction_results.get("issues", []) or []
            interventions = extraction_results.get("interventions", []) or []
            has_any_doc_issues = has_any_doc_issues or bool(issues)
            has_any_doc_interventions = has_any_doc_interventions or bool(interventions)

            doc_uuid = _safe_str(doc.get("id"))
            from_docs_issues = sorted(
                list({_safe_str(i.get("label")) for i in issues if i.get("label")})
            )
            from_docs_intr = sorted(
                list({_safe_str(i.get("name")) for i in interventions if i.get("name")})
            )

            if not from_docs_issues and doc_uuid in ext_issues_by_doc:
                from_docs_issues = sorted(list(ext_issues_by_doc.get(doc_uuid, set())))
            if not from_docs_intr and doc_uuid in ext_interventions_by_doc:
                from_docs_intr = sorted(
                    list(ext_interventions_by_doc.get(doc_uuid, set()))
                )

            input_payload.append(
                {
                    "id": doc_uuid,
                    "doc_id": _safe_str(doc.get("doc_id")),
                    "issues": from_docs_issues,
                    "interventions": from_docs_intr,
                }
            )
            num_issues_seen += len(issues)
            num_interventions_seen += len(interventions)

        if not has_any_doc_issues:
            num_issues_seen += len(ext_issues_mentions)
        if not has_any_doc_interventions:
            num_interventions_seen += len(ext_interventions_mentions)

        payload_sorted = sorted(input_payload, key=lambda d: (d["doc_id"], d["id"]))
        input_hash = hashlib.sha256(
            json.dumps(payload_sorted, sort_keys=True).encode("utf-8")
        ).hexdigest()
        source_stats = {
            "num_documents": len(documents),
            "num_issues_seen": num_issues_seen,
            "num_interventions_seen": num_interventions_seen,
            "max_document_updated_at": None,
        }

        # Cache lookup
        cache_res = (
            self.supabase.table("analysis_syntheses")
            .select("*")
            .eq("analysis_project_id", project_id)
            .execute()
        )
        if cache_res.data:
            cached = cache_res.data[0]
            model_info = cached.get("model_info") or {}
            if (
                model_info.get("input_hash") == input_hash
                and model_info.get("generation_mode") == "llm"
                and bool(model_info.get("llm_verified", False))
            ):
                key_issues_resp: List[KeyIssue] = []
                for item in cached.get("key_issues") or []:
                    src_doc_uuids = item.get("source_document_ids") or []
                    src_doc_ids = item.get("source_doc_ids") or []
                    key_issues_resp.append(
                        KeyIssue(
                            issue_theme=item.get("issue_theme", ""),
                            summary_description=item.get("summary_description", ""),
                            frequency=len(set(src_doc_uuids)) or len(set(src_doc_ids)),
                            source_doc_ids=src_doc_ids,
                        )
                    )

                interventions_resp: List[PolicyIntervention] = []
                for item in cached.get("interventions") or []:
                    interventions_resp.append(
                        PolicyIntervention(
                            intervention_name=item.get("intervention_name", ""),
                            brief_description=item.get("brief_description", ""),
                            impact_summary=item.get("impact_summary", ""),
                            supporting_doc_ids=item.get("supporting_doc_ids", []),
                        )
                    )

                key_issues_resp.sort(key=lambda x: x.frequency, reverse=True)
                interventions_resp.sort(key=lambda x: x.intervention_name)
                return SynthesisSummary(
                    executive_briefing=cached.get("executive_briefing") or "",
                    key_issues=key_issues_resp,
                    interventions=interventions_resp,
                )

        # Build mentions for LLM
        issues_mentions: List[dict] = []
        interventions_mentions: List[dict] = []
        for doc in documents:
            extraction_results = doc.get("extraction_results") or {}
            doc_uuid = _safe_str(doc.get("id"))
            doc_id = _safe_str(doc.get("doc_id"))
            for issue in extraction_results.get("issues", []) or []:
                label = _safe_str(issue.get("label"))
                if not label:
                    continue
                issues_mentions.append(
                    {
                        "analysis_document_id": doc_uuid,
                        "doc_id": doc_id,
                        "label": label,
                        "explanation": _safe_str(issue.get("explanation")),
                    }
                )
            for intr in extraction_results.get("interventions", []) or []:
                name = _safe_str(intr.get("name"))
                if not name:
                    continue
                interventions_mentions.append(
                    {
                        "analysis_document_id": doc_uuid,
                        "doc_id": doc_id,
                        "name": name,
                        "description": _safe_str(intr.get("description")),
                    }
                )
        if not issues_mentions and ext_issues_mentions:
            issues_mentions = ext_issues_mentions
        if not interventions_mentions and ext_interventions_mentions:
            interventions_mentions = ext_interventions_mentions

        def call_llm_cluster(
            issues_list: List[dict], interventions_list: List[dict]
        ) -> dict:
            system = "You are an expert in policy synthesis. Return ONLY valid JSON."
            user = (
                "Cluster semantically similar issues and interventions across documents. Create canonical, standardised entity names.\n"
                "Strict requirements:\n"
                "- Merge near-duplicates and synonyms under a single canonical name.\n"
                "- Use British English.\n"
                "- Prefer concise, Title Case names (e.g., 'High Upfront Costs').\n"
                "- Summaries must synthesise across all mentions; do not copy a single document verbatim.\n"
                "- Limit to at most 15 issue clusters and 15 intervention clusters, focusing on highest document coverage.\n"
                "- Output strictly as JSON with keys 'issues' and 'interventions'. No preface or explanation.\n\n"
                "Schema:\n"
                "{\n"
                '  "issues": [ { "issue_theme": str, "summary_description": str, "source_doc_ids": [str], "source_document_ids": [str] } ],\n'
                '  "interventions": [ { "intervention_name": str, "brief_description": str, "impact_summary": str, "supporting_doc_ids": [str], "supporting_document_ids": [str] } ]\n'
                "}\n\n"
                "Guidelines:\n- Standardise names.\n- Combine across documents.\n- Do not include any text outside JSON.\n\n"
                f"Issues input: {json.dumps(issues_list)[:12000]}\n\n"
                f"Interventions input: {json.dumps(interventions_list)[:12000]}\n"
            )
            user_escaped = user.replace("{", "{{").replace("}", "}}")
            prompt = ChatPromptTemplate.from_messages(
                [("system", system), ("user", user_escaped)]
            )
            llm = get_llm(settings.LLM_MODEL, temperature=0.0)
            resp = llm.invoke(prompt.format())
            raw = resp.content if hasattr(resp, "content") else str(resp)
            ts = (raw or "").strip()
            if ts.startswith("```"):
                ts = ts.strip("`")
                if ts.startswith("json\n"):
                    ts = ts[len("json\n") :]
            text = ts
            if "{" in ts and "}" in ts:
                try:
                    first = ts.index("{")
                    last = ts.rindex("}")
                    text = ts[first : last + 1]
                except ValueError:
                    text = ts
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                logger.warning(
                    "[synthesis] LLM JSON parse failed; using empty clusters (project_id=%s)",
                    project_id,
                )
                return {"issues": [], "interventions": []}

        issues_clusters: List[dict] = []
        interventions_clusters: List[dict] = []
        llm_ok = False
        try:
            llm_output = call_llm_cluster(issues_mentions, interventions_mentions)
            issues_clusters = llm_output.get("issues") or []
            interventions_clusters = llm_output.get("interventions") or []
            llm_ok = bool(issues_clusters or interventions_clusters)
        except Exception as e:
            logger.warning(
                "[synthesis] LLM synthesis failed for project %s, falling back: %s",
                project_id,
                e,
            )
            issues_clusters = []
            interventions_clusters = []

        if not issues_clusters and issues_mentions:
            tmp: dict[str, dict] = {}
            for m in issues_mentions:
                k = (m["label"] or "").lower()
                e = tmp.setdefault(
                    k,
                    {
                        "issue_theme": m["label"],
                        "summary_description": m.get("explanation")
                        or f"Summary for {m['label']}",
                        "source_doc_ids": set(),
                        "source_document_ids": set(),
                    },
                )
                e["source_doc_ids"].add(m["doc_id"])
                e["source_document_ids"].add(m["analysis_document_id"])
            issues_clusters = [
                {
                    "issue_theme": v["issue_theme"],
                    "summary_description": v["summary_description"],
                    "source_doc_ids": sorted(list(v["source_doc_ids"])),
                    "source_document_ids": sorted(list(v["source_document_ids"])),
                }
                for v in tmp.values()
            ]

        if not interventions_clusters and interventions_mentions:
            tmp: dict[str, dict] = {}
            for m in interventions_mentions:
                k = (m["name"] or "").lower()
                e = tmp.setdefault(
                    k,
                    {
                        "intervention_name": m["name"],
                        "brief_description": m.get("description")
                        or f"Brief description for {m['name']}",
                        "impact_summary": "Synthesised impact across documents.",
                        "supporting_doc_ids": set(),
                        "supporting_document_ids": set(),
                    },
                )
                e["supporting_doc_ids"].add(m["doc_id"])
                e["supporting_document_ids"].add(m["analysis_document_id"])
            interventions_clusters = [
                {
                    "intervention_name": v["intervention_name"],
                    "brief_description": v["brief_description"],
                    "impact_summary": v["impact_summary"],
                    "supporting_doc_ids": sorted(list(v["supporting_doc_ids"])),
                    "supporting_document_ids": sorted(
                        list(v["supporting_document_ids"])
                    ),
                }
                for v in tmp.values()
            ]

        def _compute_issue_frequency(item: dict) -> int:
            uuids = set(item.get("source_document_ids") or [])
            ids = set(item.get("source_doc_ids") or [])
            return len(uuids) or len(ids)

        def _compute_intervention_frequency(item: dict) -> int:
            uuids = set(item.get("supporting_document_ids") or [])
            ids = set(item.get("supporting_doc_ids") or [])
            return len(uuids) or len(ids)

        issues_clusters_sorted = sorted(
            issues_clusters, key=_compute_issue_frequency, reverse=True
        )
        interventions_clusters_sorted = sorted(
            interventions_clusters, key=_compute_intervention_frequency, reverse=True
        )

        top_issues_for_prompt = [
            {
                "issue_theme": i.get("issue_theme", ""),
                "summary_description": i.get("summary_description", ""),
                "frequency": _compute_issue_frequency(i),
            }
            for i in issues_clusters_sorted[:5]
        ]
        top_intr_for_prompt = [
            {
                "intervention_name": i.get("intervention_name", ""),
                "brief_description": i.get("brief_description", ""),
                "impact_summary": i.get("impact_summary", ""),
                "frequency": _compute_intervention_frequency(i),
            }
            for i in interventions_clusters_sorted[:5]
        ]

        def call_llm_executive_briefing(
            research_q: str, issues_top: List[dict], intr_top: List[dict]
        ) -> str:
            system = "You are a senior UK policy advisor. Write a concise two-paragraph executive briefing."
            user = (
                "The user's original research question is:\n"
                f'"{research_q}"\n\n'
                "Write a two-paragraph, narrative executive briefing that:\n"
                "1) Directly answers the research question,\n"
                "2) Integrates the most frequent issues as primary challenges,\n"
                "3) Highlights the most frequent interventions as the key policy levers,\n"
                "4) Concludes with a high-level assessment of the evidence base,\n"
                "5) Uses British English, professional and objective tone, and NO markdown.\n\n"
                "Structured Evidence (top 5 each):\n"
                f"Issues: {json.dumps(issues_top)}\n"
                f"Interventions: {json.dumps(intr_top)}\n"
            )
            user_escaped = user.replace("{", "{{").replace("}", "}}")
            prompt = ChatPromptTemplate.from_messages(
                [("system", system), ("user", user_escaped)]
            )
            llm = get_llm(settings.LLM_MODEL, temperature=0.2)
            resp = llm.invoke(prompt.format())
            text = (resp.content if hasattr(resp, "content") else str(resp)).strip()
            if text.startswith("```"):
                text = text.strip("`")
                if text.startswith("text\n"):
                    text = text[len("text\n") :]
            return text

        executive_briefing_text = ""
        try:
            if issues_clusters_sorted or interventions_clusters_sorted:
                executive_briefing_text = call_llm_executive_briefing(
                    research_question, top_issues_for_prompt, top_intr_for_prompt
                )
        except Exception as e:
            logger.warning(
                "[synthesis] Executive briefing LLM generation failed for project %s: %s",
                project_id,
                e,
            )
            executive_briefing_text = ""

        generation_mode = "llm" if llm_ok else "fallback"
        model_info = {
            "provider": settings.LLM_PROVIDER,
            "model": settings.LLM_MODEL,
            "temperature": 0.2,
            "prompt_version": "v1",
            "input_hash": input_hash,
            "generation_mode": generation_mode,
            "llm_verified": llm_ok,
        }
        cache_row = {
            "analysis_project_id": project_id,
            "key_issues": issues_clusters,
            "interventions": interventions_clusters,
            "executive_briefing": executive_briefing_text,
            "model_info": model_info,
            "source_stats": source_stats,
            "status": "ready",
            "updated_at": datetime.utcnow().isoformat(),
        }

        try:
            update_res = (
                self.supabase.table("analysis_syntheses")
                .update(
                    {
                        "key_issues": cache_row["key_issues"],
                        "interventions": cache_row["interventions"],
                        "executive_briefing": cache_row["executive_briefing"],
                        "model_info": cache_row["model_info"],
                        "source_stats": cache_row["source_stats"],
                        "status": cache_row["status"],
                        "updated_at": cache_row["updated_at"],
                    }
                )
                .eq("analysis_project_id", project_id)
                .execute()
            )
            if not update_res.data:
                self.supabase.table("analysis_syntheses").insert(cache_row).execute()
        except Exception:
            self.supabase.table("analysis_syntheses").insert(cache_row).execute()

        key_issues_resp: List[KeyIssue] = []
        for item in issues_clusters:
            uuids = item.get("source_document_ids") or []
            ids = item.get("source_doc_ids") or []
            key_issues_resp.append(
                KeyIssue(
                    issue_theme=item.get("issue_theme", ""),
                    summary_description=item.get("summary_description", ""),
                    frequency=len(set(uuids)) or len(set(ids)),
                    source_doc_ids=ids,
                )
            )

        interventions_resp: List[PolicyIntervention] = []
        for item in interventions_clusters:
            supp_ids = item.get("supporting_doc_ids", []) or []
            supp_uuids = item.get("supporting_document_ids", []) or []
            interventions_resp.append(
                PolicyIntervention(
                    intervention_name=item.get("intervention_name", ""),
                    brief_description=item.get("brief_description", ""),
                    impact_summary=item.get("impact_summary", ""),
                    supporting_doc_ids=supp_ids,
                    **{"frequency": len(set(supp_uuids)) or len(set(supp_ids))},
                )
            )

        key_issues_resp.sort(key=lambda x: x.frequency, reverse=True)
        interventions_resp.sort(key=lambda x: x.intervention_name)
        return SynthesisSummary(
            executive_briefing=executive_briefing_text or "",
            key_issues=key_issues_resp,
            interventions=interventions_resp,
        )

    async def get_findings(
        self,
        project_id: str,
        *,
        intervention_name: Optional[str] = None,
        issue_theme: Optional[str] = None,
    ) -> List[Finding]:
        """Flatten detailed findings for an intervention or issue.

        Args:
            project_id: Analysis project identifier.
            intervention_name: Optional filter by intervention name.
            issue_theme: Optional filter by issue label/theme.

        Returns:
            List[Finding]: Sorted findings (desc by year, then title).
        """
        docs_res = (
            self.supabase.table("analysis_documents")
            .select("*")
            .eq("analysis_project_id", project_id)
            .execute()
        )
        documents = docs_res.data or []
        if not documents:
            return []

        filt_intr = (intervention_name or "").strip()
        filt_issue = (issue_theme or "").strip()
        filt_intr_l = filt_intr.lower()
        filt_issue_l = filt_issue.lower()

        allowed_doc_uuids_from_clusters: set[str] = set()
        allowed_doc_ids_from_clusters: set[str] = set()
        try:
            cache_res = (
                self.supabase.table("analysis_syntheses")
                .select("*")
                .eq("analysis_project_id", project_id)
                .execute()
            )
            if cache_res.data:
                cached = cache_res.data[0]
                if filt_intr:
                    for intr in cached.get("interventions") or []:
                        name = str(intr.get("intervention_name") or "")
                        if name.lower() == filt_intr_l:
                            for did in intr.get("supporting_document_ids") or []:
                                allowed_doc_uuids_from_clusters.add(str(did))
                            for did in intr.get("supporting_doc_ids") or []:
                                allowed_doc_ids_from_clusters.add(str(did))
                if filt_issue:
                    for issue in cached.get("key_issues") or []:
                        name = str(issue.get("issue_theme") or "")
                        if name.lower() == filt_issue_l:
                            for did in issue.get("source_document_ids") or []:
                                allowed_doc_uuids_from_clusters.add(str(did))
                            for did in issue.get("source_doc_ids") or []:
                                allowed_doc_ids_from_clusters.add(str(did))
        except Exception as e:
            logger.warning("[findings] Failed to read synthesis cache: %s", e)

        findings: List[Finding] = []
        for doc in documents:
            extraction_results = doc.get("extraction_results") or {}
            if not extraction_results:
                continue

            interventions = extraction_results.get("interventions", []) or []
            issues = extraction_results.get("issues", []) or []
            mappings = extraction_results.get("mappings", []) or []
            results = extraction_results.get("results", []) or []

            intr_by_idx = {
                int(i.get("idx")): i
                for i in interventions
                if i is not None and i.get("idx") is not None
            }

            doc_uuid = str(doc.get("id") or "")
            doc_id = str(doc.get("doc_id") or "")
            if (filt_intr or filt_issue) and (
                allowed_doc_uuids_from_clusters or allowed_doc_ids_from_clusters
            ):
                if (
                    allowed_doc_uuids_from_clusters
                    and doc_uuid not in allowed_doc_uuids_from_clusters
                ) and (
                    allowed_doc_ids_from_clusters
                    and doc_id not in allowed_doc_ids_from_clusters
                ):
                    if (
                        allowed_doc_uuids_from_clusters
                        and not allowed_doc_ids_from_clusters
                    ):
                        if doc_uuid not in allowed_doc_uuids_from_clusters:
                            continue
                    elif (
                        allowed_doc_ids_from_clusters
                        and not allowed_doc_uuids_from_clusters
                    ):
                        if doc_id not in allowed_doc_ids_from_clusters:
                            continue
                    else:
                        continue

            include_intervention_idxs: set[int] = set()

            if filt_intr:
                for i in interventions:
                    name = str(i.get("name") or "")
                    if name and name.lower() == filt_intr_l:
                        try:
                            include_intervention_idxs.add(int(i.get("idx")))
                        except Exception:
                            continue

            if filt_issue:
                matching_issue_idxs: set[int] = set()
                for iss in issues:
                    label = str(iss.get("label") or "")
                    if label and label.lower() == filt_issue_l:
                        try:
                            matching_issue_idxs.add(int(iss.get("idx")))
                        except Exception:
                            continue
                if matching_issue_idxs:
                    for m in mappings:
                        try:
                            if int(m.get("issue_idx")) in matching_issue_idxs:
                                include_intervention_idxs.add(
                                    int(m.get("intervention_idx"))
                                )
                        except Exception:
                            continue
                else:
                    for i in interventions:
                        try:
                            include_intervention_idxs.add(int(i.get("idx")))
                        except Exception:
                            continue

            if not filt_intr and not filt_issue:
                continue

            for res in results:
                try:
                    intr_idx = int(res.get("intervention_idx"))
                except Exception:
                    continue
                if intr_idx not in include_intervention_idxs:
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
                        doc.get("landing_page_url")
                        or doc.get("pdf_url")
                        or doc.get("url")
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
                findings.append(finding)

        findings.sort(key=lambda f: (f.Year or 0, f.SourceTitle or ""), reverse=True)
        return findings
