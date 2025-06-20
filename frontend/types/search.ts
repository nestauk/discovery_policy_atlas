export interface SearchParams {
    query: string
    source: 'openalex' | 'mediacloud' | 'overton'
    max_results: number
    min_citations?: number
    date_from?: string
    date_to?: string
    inclusion_criteria?: string
    extraction_fields?: string[]
    // Overton-specific fields
    source_country?: string
    source_type?: string
    topics?: string
    classifications?: string
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
  }
  
  export interface SearchResult {
    papers: Paper[]
    total_found: number
    total_screened: number
    total_relevant: number
  }