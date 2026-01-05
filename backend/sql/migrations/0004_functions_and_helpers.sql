-- Helper functions for themes, citations, and evidence coverage
-- Note: get_theme_items_rich depends on an existing theme_assignments table.

CREATE OR REPLACE FUNCTION get_theme_items_rich(p_theme_id uuid, p_item_type text)
RETURNS JSONB AS $$
DECLARE
  result JSONB;
BEGIN
  WITH items AS (
    SELECT
      ae.id,
      ae.analysis_document_id,
      COALESCE(ae.label, '') AS title,
      COALESCE(ae.description, '') AS brief_description,
      ae.raw_data,
      ae.supporting_quote,
      ad.doc_id,
      ad.title AS doc_title,
      ad.source,
      ad.landing_page_url,
      ad.year,
      ad.venue,
      ad.source_type,
      ad.source_country
    FROM analysis_extractions ae
    JOIN theme_assignments ta ON ae.id = ta.extraction_id
    LEFT JOIN analysis_documents ad ON ad.id = ae.analysis_document_id
    WHERE ta.synthesis_theme_id = p_theme_id
      AND ae.extraction_type = p_item_type
  ),
  evidence_flat AS (
    SELECT
      i.analysis_document_id,
      lower(trim(i.title)) AS label_key,
      i.title,
      i.brief_description,
      i.doc_id,
      i.doc_title,
      i.source,
      i.landing_page_url,
      i.year,
      i.venue,
      i.source_type,
      i.source_country,
      ev_text
    FROM (
      SELECT
        items.*,
        (
          SELECT jsonb_agg(ev_txt) FILTER (WHERE ev_txt IS NOT NULL AND ev_txt <> '')
          FROM (
            SELECT
              COALESCE(
                se_elem->>'quote',
                se_elem->>'text',
                se_elem #>> '{}'
              ) AS ev_txt
            FROM jsonb_array_elements(items.raw_data->'supporting_evidence') AS se_elem
            UNION ALL
            SELECT NULLIF(items.supporting_quote, '') AS ev_txt
            UNION ALL
            SELECT NULLIF(items.raw_data->>'explanation', '') AS ev_txt
          ) u
        ) AS evidence_array
      FROM items
    ) i
    CROSS JOIN LATERAL
      UNNEST(
        COALESCE(
          ARRAY(
            SELECT jsonb_array_elements_text(
              to_jsonb(COALESCE(evidence_array, '[]'::jsonb))
            )
          ),
          ARRAY[]::text[]
        )
      ) AS ev_text
  ),
  grouped AS (
    SELECT
      e.analysis_document_id,
      e.label_key,
      e.title,
      e.brief_description,
      e.doc_id,
      e.doc_title,
      e.source,
      e.landing_page_url,
      e.year,
      e.venue,
      e.source_type,
      e.source_country,
      jsonb_agg(DISTINCT e.ev_text) AS supporting_evidence
    FROM evidence_flat e
    GROUP BY
      e.analysis_document_id,
      e.label_key,
      e.title,
      e.brief_description,
      e.doc_id,
      e.doc_title,
      e.source,
      e.landing_page_url,
      e.year,
      e.venue,
      e.source_type,
      e.source_country
  )
  SELECT COALESCE(
    jsonb_agg(
      jsonb_build_object(
        'id', (g.doc_id || '::' || g.label_key),
        'title', g.title,
        'brief_description', g.brief_description,
        'frequency', 1,
        'outcomes', '[]'::jsonb,
        'supporting_evidence', COALESCE(g.supporting_evidence, '[]'::jsonb),
        'countries', '[]'::jsonb,
        'document', jsonb_build_object(
          'doc_id', g.doc_id,
          'title', g.doc_title,
          'source', g.source,
          'landing_page_url', g.landing_page_url,
          'year', g.year,
          'venue', g.venue,
          'source_type', g.source_type,
          'source_country', g.source_country
        )
      )
    ),
    '[]'::jsonb
  )
  INTO result
  FROM grouped g;

  RETURN result;
END;
$$ LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION get_citation_key(
    p_synthesis_run_id UUID,
    p_analysis_document_id UUID
) RETURNS TEXT AS $$
DECLARE
    v_citation_key TEXT;
BEGIN
    SELECT citation_key INTO v_citation_key
    FROM synthesis_citations
    WHERE synthesis_run_id = p_synthesis_run_id
      AND analysis_document_id = p_analysis_document_id;
    
    RETURN COALESCE(v_citation_key, '[Unknown Source]');
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION get_citation_key IS 
    'Returns the citation key for a document in a specific synthesis run';


CREATE OR REPLACE FUNCTION get_project_outcome_themes(
    p_project_id UUID
) RETURNS TABLE (
    id UUID,
    outcome_name TEXT,
    outcome_description TEXT,
    effect_consensus VARCHAR(20),
    positive_count INTEGER,
    negative_count INTEGER,
    null_count INTEGER,
    frequency INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        ot.id,
        ot.outcome_name,
        ot.outcome_description,
        ot.effect_consensus,
        ot.positive_count,
        ot.negative_count,
        ot.null_count,
        ot.frequency
    FROM synthesis_outcome_themes ot
    JOIN synthesis_runs sr ON sr.id = ot.synthesis_run_id
    WHERE sr.analysis_project_id = p_project_id
      AND sr.status = 'completed'
    ORDER BY sr.created_at DESC, ot.frequency DESC;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION get_project_outcome_themes IS 
    'Returns outcome themes for a project from the latest completed synthesis run';


CREATE OR REPLACE FUNCTION get_project_evidence_coverage(
    p_project_id UUID
) RETURNS JSONB AS $$
DECLARE
    v_coverage JSONB;
BEGIN
    SELECT evidence_coverage INTO v_coverage
    FROM synthesis_runs
    WHERE analysis_project_id = p_project_id
      AND status = 'completed'
    ORDER BY created_at DESC
    LIMIT 1;
    
    RETURN COALESCE(v_coverage, '{}'::JSONB);
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION get_project_evidence_coverage IS 
    'Returns the evidence coverage snapshot for a project from the latest completed synthesis run';

