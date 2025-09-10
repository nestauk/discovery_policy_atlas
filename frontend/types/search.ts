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
    predicted_impact?: number  // 1-5 star rating for predicted impact
    predicted_impact_justification?: string
    // Extracted fields (dynamically added based on extraction_fields parameter)
    [key: string]: string | number | boolean | string[] | undefined
  }
  
  export interface SearchResult {
    papers: Paper[]
    total_found: number
    total_screened: number
    total_relevant: number
    download_key?: string
  }

  // Synthesis summary types (MVP)
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
  }

  export interface SynthesisSummary {
    executive_briefing: string
    key_issues: KeyIssue[]
    interventions: PolicyIntervention[]
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