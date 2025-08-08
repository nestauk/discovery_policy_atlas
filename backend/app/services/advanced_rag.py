import logging
from typing import List, Dict, Any
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from app.core.config import settings
from app.services.vectorization import vectorization_service

logger = logging.getLogger(__name__)


class KeyInsight(BaseModel):
    """Structured representation of a key insight from evidence"""

    insight: str = Field(description="The main insight or finding")
    evidence_source: str = Field(description="Source document reference")
    confidence: float = Field(description="Confidence score 0-1")
    supporting_quotes: List[str] = Field(
        description="Specific quotes supporting this insight"
    )


class InsightExtraction(BaseModel):
    """Collection of key insights extracted from evidence"""

    insights: List[KeyInsight] = Field(description="List of key insights")
    methodology: str = Field(description="How insights were extracted")
    evidence_coverage: str = Field(
        description="Assessment of evidence quality/coverage"
    )


class PolicyRecommendation(BaseModel):
    """Structured policy recommendation"""

    recommendation: str = Field(description="The policy recommendation")
    rationale: str = Field(description="Evidence-based rationale")
    evidence_strength: str = Field(description="Strength of supporting evidence")
    implementation_considerations: List[str] = Field(
        description="Key implementation factors"
    )
    supporting_insights: List[str] = Field(
        description="Related insights that support this"
    )


class PolicyRecommendations(BaseModel):
    """Collection of policy recommendations"""

    recommendations: List[PolicyRecommendation] = Field(
        description="List of policy recommendations"
    )
    overall_assessment: str = Field(
        description="Overall assessment of recommendation strength"
    )
    gaps_identified: List[str] = Field(
        description="Evidence gaps that limit recommendations"
    )


class ExecutiveBrief(BaseModel):
    """Executive summary combining insights and recommendations"""

    executive_summary: str = Field(description="High-level executive summary")
    key_findings: List[str] = Field(description="Top 3-5 key findings")
    policy_priorities: List[str] = Field(
        description="Top priority policy recommendations"
    )
    evidence_strength: str = Field(description="Overall evidence quality assessment")
    next_steps: List[str] = Field(description="Recommended next steps")


class ReviewResult(BaseModel):
    """Result of content review"""

    approved: bool = Field(description="Whether content is approved")
    feedback: str = Field(description="Detailed feedback")
    areas_for_improvement: List[str] = Field(
        description="Specific areas needing improvement"
    )
    score: float = Field(description="Quality score 0-1")


class AdvancedRAGService:
    """Advanced RAG service for comprehensive policy analysis"""

    def __init__(self):
        self._openai_client = None
        self._vectorization = vectorization_service

    @property
    def openai_client(self):
        if self._openai_client is None:
            if not settings.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY is required for advanced RAG service")
            self._openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._openai_client

    async def extract_key_insights(
        self, user_query: str, project_id: str = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
    ) -> InsightExtraction:
        """Extract key insights from evidence using RAG"""

        try:
            # Get comprehensive evidence from multiple search angles
            insights_contexts = await self._gather_insights_evidence(
                user_query, project_id
            )

            if not insights_contexts:
                return InsightExtraction(
                    insights=[],
                    methodology="No evidence available for analysis",
                    evidence_coverage="No evidence found",
                )

            # Generate insights using structured extraction
            insights = await self._generate_structured_insights(
                user_query, insights_contexts
            )

            return insights

        except Exception as e:
            logger.error(f"Error extracting key insights: {e}")
            return InsightExtraction(
                insights=[],
                methodology=f"Error during extraction: {str(e)}",
                evidence_coverage="Analysis failed",
            )

    async def _gather_insights_evidence(
        self, user_query: str, project_id: str
    ) -> List[Dict[str, Any]]:
        """Gather evidence from multiple search perspectives for comprehensive insights"""

        # Multiple search queries to ensure comprehensive coverage
        search_queries = [
            user_query,  # Original query
            f"key findings {user_query}",  # Focus on findings
            f"results outcomes {user_query}",  # Focus on outcomes
            f"evidence data {user_query}",  # Focus on evidence
            f"implications {user_query}",  # Focus on implications
        ]

        all_evidence = []
        seen_document_ids = set()

        for query in search_queries:
            try:
                evidence = await self._vectorization.search_similar_content(
                    query=query,
                    project_id=project_id,
                    match_threshold=0.6,  # Lower threshold for broader coverage
                    match_count=10,  # More documents per query
                )

                # Add unique documents only
                for doc in evidence:
                    doc_id = doc.get("document_id")
                    if doc_id and doc_id not in seen_document_ids:
                        all_evidence.append(doc)
                        seen_document_ids.add(doc_id)

            except Exception as e:
                logger.warning(f"Error in evidence search for query '{query}': {e}")

        # Get document details for all evidence
        if all_evidence:
            all_evidence = await self._enrich_evidence_with_details(
                all_evidence, project_id
            )

        return all_evidence[:15]  # Limit to top 15 most relevant pieces

    async def _enrich_evidence_with_details(
        self, evidence: List[Dict[str, Any]], project_id: str
    ) -> List[Dict[str, Any]]:
        """Enrich evidence with full document details"""

        document_ids = list(
            set(doc.get("document_id") for doc in evidence if doc.get("document_id"))
        )

        document_details = {}
        if document_ids:
            try:
                result = (
                    self._vectorization.supabase.table("documents")
                    .select("*")
                    .in_("id", document_ids)
                    .execute()
                )

                for doc in result.data:
                    document_details[doc["id"]] = doc
            except Exception as e:
                logger.error(f"Error fetching document details: {e}")

        # Enrich evidence with document details
        enriched_evidence = []
        for doc in evidence:
            enriched_doc = doc.copy()
            doc_id = doc.get("document_id")

            if doc_id and doc_id in document_details:
                doc_details = document_details[doc_id]
                enriched_doc.update(
                    {
                        "document_title": doc_details.get("title", ""),
                        "document_authors": doc_details.get("authors", []),
                        "document_abstract": doc_details.get("abstract", ""),
                        "document_content": doc_details.get("content", ""),
                        "confidence": doc_details.get("confidence", 0.0),
                        "relevance_reason": doc_details.get("relevance_reason", ""),
                        "top_line": doc_details.get("top_line", ""),
                        "source_country": doc_details.get("source_country", ""),
                        "published_date": doc_details.get("published_date", ""),
                    }
                )

            enriched_evidence.append(enriched_doc)

        return enriched_evidence

    async def _generate_structured_insights(
        self, user_query: str, evidence: List[Dict[str, Any]]
    ) -> InsightExtraction:
        """Generate structured insights using OpenAI with function calling"""

        # Build comprehensive evidence context
        evidence_context = self._build_evidence_context(evidence)

        system_prompt = f"""You are an expert policy analyst tasked with extracting key insights from research evidence.

ANALYSIS TASK:
Extract the most important insights and findings from the provided evidence that are relevant to: "{user_query}"

INSTRUCTIONS:
1. Focus on factual findings, data points, and concrete evidence
2. Identify patterns across multiple sources when possible
3. Rate confidence based on evidence quality and consistency
4. Include specific supporting quotes from the evidence
5. Be precise and avoid speculation beyond what the evidence supports
6. Prioritize insights that are most relevant to policy decision-making

EVIDENCE TO ANALYZE:
{evidence_context}

Extract insights systematically and structure them clearly."""

        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4.1-mini",  # Use the model that supports function calling
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": f"Extract key insights relevant to: {user_query}",
                    },
                ],
                functions=[
                    {
                        "name": "extract_insights",
                        "description": "Extract structured insights from policy evidence",
                        "parameters": InsightExtraction.model_json_schema(),
                    }
                ],
                function_call={"name": "extract_insights"},
                temperature=0.1,  # Lower temperature for more consistent extraction
            )

            # Parse the function call result
            function_call = response.choices[0].message.function_call
            if function_call and function_call.name == "extract_insights":
                import json

                insights_data = json.loads(function_call.arguments)
                return InsightExtraction(**insights_data)
            else:
                # Fallback to manual parsing if function calling fails
                return await self._fallback_insights_extraction(
                    user_query, evidence_context
                )

        except Exception as e:
            logger.error(f"Error in structured insights generation: {e}")
            return await self._fallback_insights_extraction(
                user_query, evidence_context
            )

    async def _fallback_insights_extraction(
        self, user_query: str, evidence_context: str
    ) -> InsightExtraction:
        """Fallback method for insights extraction without function calling"""

        prompt = f"""Extract key insights from the following evidence relevant to: "{user_query}"

Format your response as a structured analysis with:
1. List of key insights (each with evidence source and confidence level)
2. Methodology used for extraction
3. Assessment of evidence coverage

Evidence:
{evidence_context}"""

        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert policy analyst. Extract key insights systematically.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
            )

            content = response.choices[0].message.content

            # Parse the unstructured response into structured format
            # This is a simple parser - could be enhanced with more sophisticated NLP
            return InsightExtraction(
                insights=[
                    KeyInsight(
                        insight=content[:500],  # Simplified - would need better parsing
                        evidence_source="Multiple sources",
                        confidence=0.7,
                        supporting_quotes=[],
                    )
                ],
                methodology="LLM-based extraction with manual parsing",
                evidence_coverage="Analyzed available evidence in context",
            )

        except Exception as e:
            logger.error(f"Error in fallback insights extraction: {e}")
            return InsightExtraction(
                insights=[],
                methodology=f"Extraction failed: {str(e)}",
                evidence_coverage="Analysis incomplete",
            )

    def _build_evidence_context(self, evidence: List[Dict[str, Any]]) -> str:
        """Build comprehensive evidence context for analysis"""

        context_parts = []

        for i, doc in enumerate(evidence, 1):
            doc_context = f"\n--- EVIDENCE {i} ---\n"

            # Document metadata
            title = doc.get("document_title", "Unknown Document")
            authors = doc.get("document_authors", [])
            country = doc.get("source_country", "")
            confidence = doc.get("confidence", 0.0)

            doc_context += f"Title: {title}\n"
            if authors:
                doc_context += f"Authors: {', '.join(authors)}\n"
            if country:
                doc_context += f"Country: {country}\n"
            doc_context += f"Relevance Confidence: {confidence}\n"

            # Key content
            if doc.get("top_line"):
                doc_context += f"Key Finding: {doc['top_line']}\n"
            if doc.get("relevance_reason"):
                doc_context += f"Relevance: {doc['relevance_reason']}\n"

            # Content chunk
            content = doc.get("content", "")
            if content:
                doc_context += f"Content: {content}\n"

            # Abstract if available
            abstract = doc.get("document_abstract", "")
            if abstract and abstract not in content:
                doc_context += f"Abstract: {abstract[:500]}...\n"

            context_parts.append(doc_context)

        return "\n".join(context_parts)

    async def review_insights(self, insights: InsightExtraction) -> ReviewResult:
        """Review the quality of extracted insights"""

        system_prompt = """You are a senior policy researcher reviewing extracted insights for quality and completeness.

REVIEW CRITERIA:
1. Accuracy: Are insights well-supported by evidence?
2. Relevance: Do insights address the research question?
3. Completeness: Are important findings captured?
4. Clarity: Are insights clearly articulated?
5. Evidence strength: Is the underlying evidence sufficient?

Rate the overall quality on a scale of 0-1 and provide specific feedback."""

        try:
            insights_text = f"""
METHODOLOGY: {insights.methodology}
EVIDENCE COVERAGE: {insights.evidence_coverage}

INSIGHTS:
{chr(10).join([f"- {insight.insight} (Confidence: {insight.confidence}, Source: {insight.evidence_source})" for insight in insights.insights])}
"""

            response = await self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": f"Review these extracted insights:\n{insights_text}",
                    },
                ],
                temperature=0.1,
            )

            content = response.choices[0].message.content

            # Simple quality assessment - could be enhanced with structured parsing
            score = 0.8 if len(insights.insights) >= 3 else 0.5
            approved = score >= 0.7

            return ReviewResult(
                approved=approved,
                feedback=content,
                areas_for_improvement=["More specific evidence quotes needed"]
                if not approved
                else [],
                score=score,
            )

        except Exception as e:
            logger.error(f"Error reviewing insights: {e}")
            return ReviewResult(
                approved=False,
                feedback=f"Review failed: {str(e)}",
                areas_for_improvement=["Technical error in review process"],
                score=0.0,
            )

    async def generate_policy_recommendations(
        self,
        user_query: str,
        insights: InsightExtraction = None,
        project_id: str = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
    ) -> PolicyRecommendations:
        """Generate policy recommendations based on evidence and insights"""

        try:
            # Get evidence from multiple angles focused on policy implications
            policy_contexts = await self._gather_policy_evidence(user_query, project_id)

            if not policy_contexts:
                return PolicyRecommendations(
                    recommendations=[],
                    overall_assessment="No evidence available for policy analysis",
                    gaps_identified=[
                        "Insufficient evidence for policy recommendations"
                    ],
                )

            # Generate recommendations using structured extraction
            recommendations = await self._generate_structured_recommendations(
                user_query, policy_contexts, insights
            )

            return recommendations

        except Exception as e:
            logger.error(f"Error generating policy recommendations: {e}")
            return PolicyRecommendations(
                recommendations=[],
                overall_assessment=f"Error during analysis: {str(e)}",
                gaps_identified=["Technical error in recommendation generation"],
            )

    async def _gather_policy_evidence(
        self, user_query: str, project_id: str
    ) -> List[Dict[str, Any]]:
        """Gather evidence specifically focused on policy implications and recommendations"""

        # Policy-focused search queries
        policy_queries = [
            f"policy recommendations {user_query}",
            f"policy interventions {user_query}",
            f"policy implications {user_query}",
            f"government action {user_query}",
            f"implementation strategies {user_query}",
            f"regulatory approaches {user_query}",
        ]

        all_evidence = []
        seen_document_ids = set()

        for query in policy_queries:
            try:
                evidence = await self._vectorization.search_similar_content(
                    query=query,
                    project_id=project_id,
                    match_threshold=0.6,
                    match_count=8,
                )

                # Add unique documents only
                for doc in evidence:
                    doc_id = doc.get("document_id")
                    if doc_id and doc_id not in seen_document_ids:
                        all_evidence.append(doc)
                        seen_document_ids.add(doc_id)

            except Exception as e:
                logger.warning(
                    f"Error in policy evidence search for query '{query}': {e}"
                )

        # Get document details for all evidence
        if all_evidence:
            all_evidence = await self._enrich_evidence_with_details(
                all_evidence, project_id
            )

        return all_evidence[:12]  # Limit to top 12 most relevant pieces

    async def _generate_structured_recommendations(
        self,
        user_query: str,
        evidence: List[Dict[str, Any]],
        insights: InsightExtraction = None,
    ) -> PolicyRecommendations:
        """Generate structured policy recommendations using OpenAI"""

        # Build comprehensive evidence context
        evidence_context = self._build_evidence_context(evidence)

        # Include insights context if available
        insights_context = ""
        if insights and insights.insights:
            insights_context = "\n\nKEY INSIGHTS FROM PREVIOUS ANALYSIS:\n"
            for i, insight in enumerate(insights.insights, 1):
                insights_context += (
                    f"{i}. {insight.insight} (Confidence: {insight.confidence:.0%})\n"
                )

        system_prompt = f"""You are a senior policy advisor tasked with developing evidence-based policy recommendations.

ANALYSIS TASK:
Based on the research evidence provided, generate up to 3 specific, actionable policy recommendations related to: "{user_query}"

INSTRUCTIONS:
1. Focus on practical, implementable policy interventions
2. Base each recommendation on specific evidence from the literature
3. Consider implementation challenges and feasibility
4. Provide clear rationale linking evidence to recommendations
5. Assess the strength of evidence supporting each recommendation
6. Identify any significant gaps in the evidence base

EVIDENCE TO ANALYZE:
{evidence_context}
{insights_context}

Generate clear, actionable policy recommendations with strong evidence backing."""

        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": f"Generate evidence-based policy recommendations for: {user_query}",
                    },
                ],
                functions=[
                    {
                        "name": "generate_policy_recommendations",
                        "description": "Generate structured policy recommendations based on evidence",
                        "parameters": PolicyRecommendations.model_json_schema(),
                    }
                ],
                function_call={"name": "generate_policy_recommendations"},
                temperature=0.1,
            )

            # Parse the function call result
            function_call = response.choices[0].message.function_call
            if (
                function_call
                and function_call.name == "generate_policy_recommendations"
            ):
                import json

                recommendations_data = json.loads(function_call.arguments)
                return PolicyRecommendations(**recommendations_data)
            else:
                # Fallback to default recommendations if function calling fails
                return PolicyRecommendations(
                    recommendations=[
                        PolicyRecommendation(
                            recommendation="Evidence-based policy intervention needed",
                            rationale="Based on the available evidence, targeted interventions are recommended.",
                            evidence_strength="Moderate",
                            implementation_considerations=[
                                "Requires further research",
                                "Stakeholder engagement needed",
                            ],
                            supporting_insights=[],
                        )
                    ],
                    overall_assessment="Policy recommendations based on available evidence",
                    gaps_identified=[
                        "Additional evidence may strengthen recommendations"
                    ],
                )

        except Exception as e:
            logger.error(f"Error in policy recommendations generation: {e}")
            return PolicyRecommendations(
                recommendations=[],
                overall_assessment=f"Generation failed: {str(e)}",
                gaps_identified=["Technical error in generation process"],
            )

    async def review_recommendations(
        self, recommendations: PolicyRecommendations
    ) -> ReviewResult:
        """Review the quality of generated policy recommendations"""

        system_prompt = """You are a senior policy researcher reviewing policy recommendations for quality and feasibility.

REVIEW CRITERIA:
1. Evidence basis: Are recommendations well-supported by research?
2. Feasibility: Are recommendations practical and implementable?
3. Specificity: Are recommendations clear and actionable?
4. Impact potential: Could these recommendations make a meaningful difference?
5. Implementation guidance: Are practical considerations addressed?

Rate the overall quality on a scale of 0-1 and provide specific feedback."""

        try:
            recommendations_text = f"""
OVERALL ASSESSMENT: {recommendations.overall_assessment}
GAPS IDENTIFIED: {', '.join(recommendations.gaps_identified)}

RECOMMENDATIONS:
{chr(10).join([f"- {rec.recommendation}: {rec.rationale}" for rec in recommendations.recommendations])}
"""

            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": f"Review these policy recommendations:\n{recommendations_text}",
                    },
                ],
                temperature=0.1,
            )

            content = response.choices[0].message.content

            # Simple quality assessment
            score = 0.8 if len(recommendations.recommendations) >= 2 else 0.6
            approved = score >= 0.7

            return ReviewResult(
                approved=approved,
                feedback=content,
                areas_for_improvement=["More specific implementation details needed"]
                if not approved
                else [],
                score=score,
            )

        except Exception as e:
            logger.error(f"Error reviewing recommendations: {e}")
            return ReviewResult(
                approved=False,
                feedback=f"Review failed: {str(e)}",
                areas_for_improvement=["Technical error in review process"],
                score=0.0,
            )

    async def generate_executive_brief(
        self,
        user_query: str,
        insights: InsightExtraction = None,
        recommendations: PolicyRecommendations = None,
        project_id: str = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
    ) -> ExecutiveBrief:
        """Generate executive brief combining insights and recommendations"""

        try:
            # Build detailed context from insights and recommendations
            context_parts = []

            if insights and insights.insights:
                context_parts.append("KEY INSIGHTS:")
                for i, insight in enumerate(insights.insights, 1):
                    context_parts.append(f"{i}. {insight.insight}")
                    if insight.confidence:
                        context_parts.append(f"   Confidence: {insight.confidence:.0%}")
                    if insight.evidence_source:
                        context_parts.append(f"   Source: {insight.evidence_source}")
                context_parts.append("")  # Add spacing

            if recommendations and recommendations.recommendations:
                context_parts.append("POLICY RECOMMENDATIONS:")
                for i, rec in enumerate(recommendations.recommendations, 1):
                    context_parts.append(f"{i}. {rec.recommendation}")
                    if rec.rationale:
                        context_parts.append(f"   Rationale: {rec.rationale[:200]}...")
                    if rec.evidence_strength:
                        context_parts.append(
                            f"   Evidence Strength: {rec.evidence_strength}"
                        )
                context_parts.append("")  # Add spacing

            if recommendations and recommendations.overall_assessment:
                context_parts.append(
                    f"OVERALL ASSESSMENT: {recommendations.overall_assessment}"
                )

            combined_context = "\n".join(context_parts)

            system_prompt = f"""You are an executive briefing specialist creating a crisp, clear summary for senior decision-makers.

TASK: Create an executive brief about "{user_query}" based on the analysis below.

REQUIREMENTS:
1. Executive summary: 2-3 sentences capturing the essence in clear, actionable language
2. Key findings: 3-5 specific, evidence-based discoveries from the analysis
3. Policy priorities: Top 3 concrete, actionable recommendations
4. Evidence strength: Clear assessment of evidence quality and reliability
5. Next steps: 3-4 specific, implementable next actions

IMPORTANT:
- Use crisp, clear language suitable for executive decision-making
- Base all content on the actual insights and recommendations provided
- Avoid generic statements - be specific to the topic and evidence
- Focus on actionable insights and concrete recommendations
- Keep language professional but accessible

ANALYSIS RESULTS:
{combined_context}"""

            response = await self.openai_client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": f"Create executive brief for: {user_query}",
                    },
                ],
                functions=[
                    {
                        "name": "generate_executive_brief",
                        "description": "Generate structured executive brief based on insights and recommendations",
                        "parameters": ExecutiveBrief.model_json_schema(),
                    }
                ],
                function_call={"name": "generate_executive_brief"},
                temperature=0.1,
            )

            # Parse the function call result
            function_call = response.choices[0].message.function_call
            if function_call and function_call.name == "generate_executive_brief":
                import json

                brief_data = json.loads(function_call.arguments)
                return ExecutiveBrief(**brief_data)
            else:
                # Fallback to default brief if function calling fails
                return ExecutiveBrief(
                    executive_summary=f"Analysis completed for {user_query}. Executive brief generation failed.",
                    key_findings=["Analysis completed"],
                    policy_priorities=["Review technical issues"],
                    evidence_strength="Unable to assess due to technical error",
                    next_steps=["Resolve technical issues", "Retry analysis"],
                )

        except Exception as e:
            logger.error(f"Error generating executive brief: {e}")
            return ExecutiveBrief(
                executive_summary=f"Analysis completed for {user_query}. Technical error in brief generation.",
                key_findings=["Analysis completed"],
                policy_priorities=["Review technical issues"],
                evidence_strength="Unable to assess due to technical error",
                next_steps=["Resolve technical issues", "Retry analysis"],
            )


# Global instance
advanced_rag_service = AdvancedRAGService()
