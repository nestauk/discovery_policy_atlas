export interface SearchParams {
    query: string
    source: 'openalex' | 'overton'
    max_results: number
    min_citations?: number
    date_from?: string
    date_to?: string
    inclusion_criteria?: string
    extraction_fields?: string[]
    // Overton-specific fields
    source_country?: string
    source_type?: string
    topics?: string[]
    classifications?: string
    semantic_search?: boolean
  }
  
  export interface Paper {
    id: string
    title: string
    publication_year: number
    cited_by_count: number
    doi: string
    abstract?: string
    authors: string[]
    venue?: string
    is_relevant: boolean
    relevance_reason?: string
    confidence?: number
    // Additional fields for Overton documents
    topics?: string[]
    source_country?: string
    source_type?: string
    published_on?: string
    overton_url?: string
    // AI-generated summary
    top_line?: string
    // URL fields
    landing_page_url?: string
    // Evidence categorisation fields (9-category hierarchy)
    evidence_category?: string
    evidence_confidence?: number
    evidence_category_reasoning?: string
    evidence_category_rank?: number
    // Processing status fields
    full_text_available?: boolean
    extraction_status?: string
    text_source?: string  // "full_text" or "abstract" - what was used for extraction
    study_strength?: string  // strongest study type letter from interventions
    sample_size?: number  // largest sample size from interventions
    source?: string  // "openalex" or "overton"
    // Evidence assessment fields
    evidence_strength?: number  // 1-5 star rating for evidence quality
    evidence_strength_justification?: string
  impact_score?: number | null // 1-5 impact score (document-level), null when unassessable
  impact_score_label?: string
  impact_score_breakdown?: Record<string, unknown>
    // Extracted fields (dynamically added based on extraction_fields parameter)
    [key: string]:
      | string
      | number
      | boolean
      | string[]
      | Record<string, unknown>
      | undefined
  }
  
  export interface SearchResult {
    papers: Paper[]
    total_found: number
    total_screened: number
    total_relevant: number
    download_key?: string
  }

  // Synthesis summary types (Enhanced)
  export type VerdictType = 
    | 'well_evidenced_increase'
    | 'well_evidenced_decrease'
    | 'evidenced_increase'
    | 'evidenced_decrease'
    | 'suggested_increase'
    | 'suggested_decrease'
    | 'contested'
    | 'no_effect'
    | 'insufficient_evidence'
    | 'probable_contribution';

  export type SemanticMagnitudeType =
    | 'transformational'
    | 'substantial'
    | 'moderate'
    | 'marginal'
    | 'unknown';

  export type CausalityClaimType = 'attribution' | 'contribution' | 'correlation';

export interface MagnitudeDetail {
  direction: 'increase' | 'decrease' | 'contested';
  bucket_counts: Record<string, number>;
  source_count: number;
  total_sources: number;
  measurement_count: number;
  dominant_scale: string;
  thresholds: string;
}

export interface CausalityDetail {
  attribution: number;
  contribution: number;
  correlation: number;
}

  export interface TransferabilityBreakdown {
    inner_setting: string;
    population: string;
    geography: string;
    notes?: Record<string, string>;
    data_availability?: Record<string, string>;
    context_fit_rating?: string;
  implementation_requirements_rating?: 'Low' | 'Medium' | 'High' | 'Unknown';
    implementation_constraints_specified?: boolean;
    implementation_evidence?: Record<string, string>;
    implementation_constraints?: Record<string, string>;
  implementation_exceeds_tolerance?: Record<string, boolean>;
  }

  export interface RiskTheme {
    theme_name: string;
    summary_description: string;
    frequency: number;
    source_doc_ids: string[];
    has_harm_warning: boolean;
    linked_intervention_theme_id?: string;
    linked_interventions?: Array<{
      intervention_theme_id: string;
      link_strength: string;
    }>;
  }
  export interface KeyIssue {
    issue_theme: string
    summary_description: string
    frequency: number
    source_doc_ids: string[]
  }

  export interface PolicyIntervention {
    intervention_name: string
    brief_description: string
    impact_summary: string
    supporting_doc_ids: string[]
    frequency?: number
    effect_consensus?: 'increase' | 'decrease' | 'mixed' | 'no change' | 'insufficient'
    positive_count?: number
    negative_count?: number
    null_count?: number
    sample_effect_sizes?: string[]
    countries?: string[]
    study_types?: Record<string, number>
    related_outcomes?: string[]
    transferability_rating?: string
    transferability_note?: string
    transferability_breakdown?: TransferabilityBreakdown
  }

  export interface CitationInfo {
    citation_key: string
    citation_number?: number
    doc_id?: string
    analysis_document_id: string
    author_short?: string
    year?: number
    title?: string
    url?: string
    supporting_quote?: string
    chunk_id?: string
  }

  export interface EvidenceCoverageSnapshot {
    total_screened: number
    total_synthesised: number
    study_types: Record<string, number>
    source_types: Record<string, number>
    evidence_categories?: Record<string, number>
    countries: Record<string, number>
    years: Record<number, number>
    overall_strength: string
    gaps: string[]
  }

  export interface OutcomeTheme {
    outcome_name: string
    outcome_description: string
    effect_consensus: 'increase' | 'decrease' | 'mixed' | 'no change' | 'insufficient'
    positive_count: number
    negative_count: number
    null_count: number
    sample_effect_sizes: string[]
    frequency: number
    source_doc_ids: string[]
    verdict_label?: VerdictType
    verdict_description?: string
    discord_flag?: boolean
    discord_reason?: string
    predicted_magnitude?: SemanticMagnitudeType
  magnitude_detail?: MagnitudeDetail
    intervention_theme_id?: string
  primary_causal_mechanism?: CausalityClaimType
  causal_mechanism_detail?: CausalityDetail
  }

  // Structured briefing types for frontend rendering
  export interface EvidenceSnapshotRow {
    metric: string
    detail: string
  }

  export interface OutcomeEffect {
    outcome_theme: string
    direction: 'increase' | 'decrease' | 'no change' | 'mixed' | 'insufficient'
    positive_count: number
    negative_count: number
    null_count: number
  }

  export interface InterventionTableRow {
    intervention_name: string
    citation_numbers: number[]
    context: string
    key_study_description?: string
    key_study_citation?: number
  delivery_features?: string[]
  subgroup_effects?: string[]
    impact_narrative: string
    outcome_effects: OutcomeEffect[]
  }

  export interface RecommendationItem {
    number: number
    title: string
    description: string
    implementation_option?: string
    citation_numbers: number[]
  }

  export interface TopCitationItem {
    citation_number: number
    title: string
    author_year: string
    reason: string
    url?: string
  }

  export interface BackgroundSection {
    title: string
    paragraphs: string[]
    citation_numbers_used: number[]
  }

export interface SynthesisSection {
  title: string
  content_type: 'paragraphs' | 'bullets'
  paragraphs: string[]
  bullets: string[]
  citation_numbers_used: number[]
}

  export interface CoreAnswer {
    query: string
    answer: string
    directive: string
  }

  export interface StructuredBriefing {
    core_answer: CoreAnswer
    evidence_snapshot: EvidenceSnapshotRow[]
    evidence_snapshot_summary: string
    background_section?: BackgroundSection
    interventions_table: InterventionTableRow[]
  synthesis_sections?: SynthesisSection[]
    recommendations: RecommendationItem[]
    top_citations: TopCitationItem[]
    follow_up_suggestions: string[]
  }

  export interface SynthesisSummary {
    executive_briefing: string
    structured_briefing?: StructuredBriefing  // New structured output
    key_issues: KeyIssue[]
    interventions: PolicyIntervention[]
    // Enhanced fields
    outcome_themes?: OutcomeTheme[]
    evidence_coverage?: EvidenceCoverageSnapshot
    citation_map?: Record<string, CitationInfo>
    risk_themes?: RiskTheme[]
  }

  // Drill-down finding interface (matches backend endpoint shape)
  export interface Finding {
    SourceTitle: string
    Source?: string
    DocId?: string
    Year?: number
    Url?: string
    Intervention?: string
    StudyDesign?: string
    Outcome?: string
    EffectDirection?: string
    EffectSizeType?: string
    EffectSize?: string
    PValue?: string
    Uncertainty?: string
    Evidence: string[]
  }
