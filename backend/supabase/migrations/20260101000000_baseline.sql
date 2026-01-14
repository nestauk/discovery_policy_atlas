-- Baseline migration: Production schema as of 2026-01-05
-- This captures the exact state of the production database

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS "vector" WITH SCHEMA "public";

-- ============================================================================
-- FUNCTIONS
-- ============================================================================

CREATE OR REPLACE FUNCTION "public"."get_citation_key"("p_synthesis_run_id" "uuid", "p_analysis_document_id" "uuid") RETURNS "text"
    LANGUAGE "plpgsql" STABLE
    AS $$
DECLARE
    v_citation_key TEXT;
BEGIN
    SELECT citation_key INTO v_citation_key
    FROM synthesis_citations
    WHERE synthesis_run_id = p_synthesis_run_id
      AND analysis_document_id = p_analysis_document_id;
    
    RETURN COALESCE(v_citation_key, '[Unknown Source]');
END;
$$;

COMMENT ON FUNCTION "public"."get_citation_key"("p_synthesis_run_id" "uuid", "p_analysis_document_id" "uuid") IS 'Returns the citation key for a document in a specific synthesis run';


CREATE OR REPLACE FUNCTION "public"."get_network_data_for_project"("p_project_id" "uuid") RETURNS "jsonb"
    LANGUAGE "plpgsql"
    AS $$
DECLARE
    latest_run_id uuid;
    network_data jsonb;
BEGIN
    SELECT sr.id INTO latest_run_id
    FROM synthesis_runs sr
    JOIN analysis_projects ap ON sr.analysis_project_id = ap.id
    WHERE ap.id = p_project_id AND sr.status = 'completed'
    ORDER BY sr.created_at DESC
    LIMIT 1;

    IF latest_run_id IS NULL THEN
        RETURN '{"nodes": [], "edges": []}'::jsonb;
    END IF;

    WITH
    themes AS (
        SELECT id, theme_name, theme_type
        FROM synthesis_themes
        WHERE synthesis_run_id = latest_run_id
          AND theme_type IN ('intervention', 'outcome')
    ),
    intervention_extractions AS (
        SELECT
            ae.id,
            ae.document_id,
            (ae.raw_data->>'idx')::int AS intervention_idx,
            t.theme_name AS intervention_theme
        FROM analysis_extractions ae
        JOIN theme_assignments ta ON ae.id = ta.extraction_id
        JOIN themes t ON ta.synthesis_theme_id = t.id
        WHERE ae.extraction_type = 'intervention' AND t.theme_type = 'intervention'
    ),
    result_extractions AS (
        SELECT
            ae.id,
            ae.document_id,
            (ae.raw_data->>'intervention_idx')::int AS intervention_idx,
            t.theme_name AS outcome_theme
        FROM analysis_extractions ae
        JOIN theme_assignments ta ON ae.id = ta.extraction_id
        JOIN themes t ON ta.synthesis_theme_id = t.id
        WHERE ae.extraction_type = 'result' AND t.theme_type = 'outcome'
    )
    SELECT
        jsonb_build_object(
            'nodes', (
                SELECT jsonb_agg(
                    jsonb_build_object('id', theme_name, 'type', theme_type)
                )
                FROM themes
            ),
            'edges', (
                SELECT jsonb_agg(
                    jsonb_build_object(
                        'source', ie.intervention_theme,
                        'target', re.outcome_theme,
                        'weight', COUNT(*)
                    )
                )
                FROM intervention_extractions ie
                JOIN result_extractions re
                  ON ie.document_id = re.document_id
                 AND ie.intervention_idx = re.intervention_idx
                GROUP BY ie.intervention_theme, re.outcome_theme
            )
        )
    INTO network_data;

    RETURN COALESCE(network_data, '{"nodes": [], "edges": []}'::jsonb);
END;
$$;


CREATE OR REPLACE FUNCTION "public"."get_project_evidence_coverage"("p_project_id" "uuid") RETURNS "jsonb"
    LANGUAGE "plpgsql" STABLE
    AS $$
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
$$;

COMMENT ON FUNCTION "public"."get_project_evidence_coverage"("p_project_id" "uuid") IS 'Returns the evidence coverage snapshot for a project from the latest completed synthesis run';


CREATE OR REPLACE FUNCTION "public"."get_project_outcome_themes"("p_project_id" "uuid") RETURNS TABLE("id" "uuid", "outcome_name" "text", "outcome_description" "text", "effect_consensus" character varying, "positive_count" integer, "negative_count" integer, "null_count" integer, "frequency" integer)
    LANGUAGE "plpgsql" STABLE
    AS $$
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
$$;

COMMENT ON FUNCTION "public"."get_project_outcome_themes"("p_project_id" "uuid") IS 'Returns outcome themes for a project from the latest completed synthesis run';


CREATE OR REPLACE FUNCTION "public"."get_project_thematic_groups"("p_project_id" "uuid") RETURNS TABLE("id" "text", "theme_title" "text", "theme_summary" "text", "item_count_string" "text")
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    RETURN QUERY
    WITH latest_run AS (
        SELECT sr.id AS run_id
        FROM synthesis_runs sr
        WHERE sr.analysis_project_id = p_project_id
          AND sr.status = 'completed'
        ORDER BY sr.created_at DESC
        LIMIT 1
    ),
    theme_counts AS (
        SELECT
            st.id::text AS theme_id,
            st.theme_name AS theme_name,
            st.summary_description AS summary_description,
            SUM(CASE WHEN st.theme_type = 'intervention' THEN 1 ELSE 0 END) AS intervention_count,
            SUM(CASE WHEN st.theme_type = 'issue' THEN 1 ELSE 0 END) AS issue_count
        FROM synthesis_themes st
        JOIN latest_run lr ON st.synthesis_run_id = lr.run_id
        GROUP BY st.id, st.theme_name, st.summary_description
    )
    SELECT
        tc.theme_id AS id,
        tc.theme_name AS theme_title,
        COALESCE(tc.summary_description, '') AS theme_summary,
        TRIM(BOTH ', ' FROM
            (CASE WHEN tc.intervention_count > 0 THEN tc.intervention_count || ' Interventions' ELSE '' END) ||
            (CASE WHEN tc.intervention_count > 0 AND tc.issue_count > 0 THEN ', ' ELSE '' END) ||
            (CASE WHEN tc.issue_count > 0 THEN tc.issue_count || ' Issues' ELSE '' END)
        ) AS item_count_string
    FROM theme_counts tc
    ORDER BY tc.theme_name;
END;
$$;


CREATE OR REPLACE FUNCTION "public"."get_project_thematic_groups_by_type"("p_project_id" "uuid", "p_theme_type" "text") RETURNS TABLE("id" "uuid", "theme_title" "text", "theme_summary" "text", "item_count" integer)
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  RETURN QUERY
  SELECT
    st.id,
    st.theme_name AS theme_title,
    COALESCE(st.summary_description, '') AS theme_summary,
    (
      SELECT COUNT(
               DISTINCT lower(regexp_replace(trim(ae.label), '\s+', ' ', 'g'))
             )::int
      FROM theme_assignments ta
      JOIN analysis_extractions ae ON ae.id = ta.extraction_id
      WHERE ta.synthesis_theme_id = st.id
        AND ae.extraction_type = p_theme_type
        AND ae.label IS NOT NULL
    ) AS item_count
  FROM synthesis_themes st
  JOIN synthesis_runs sr ON sr.id = st.synthesis_run_id
  WHERE sr.analysis_project_id = p_project_id
    AND st.theme_type = p_theme_type
  ORDER BY st.theme_name;
END;
$$;


CREATE OR REPLACE FUNCTION "public"."get_theme_items"("p_theme_id" "uuid", "p_item_type" "text") RETURNS TABLE("id" "uuid", "title" "text", "source_count" integer, "countries" "text"[], "summary" "text")
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    RETURN QUERY
    WITH assigned AS (
        SELECT ta.extraction_id::uuid AS extraction_id
        FROM theme_assignments ta
        WHERE ta.synthesis_theme_id = p_theme_id
    )
    SELECT
        ae.id::uuid AS id,
        CASE 
            WHEN ae.extraction_type = 'intervention' 
                THEN COALESCE(ae.label, (ae.raw_data->>'name'))
            WHEN ae.extraction_type = 'issue'
                THEN COALESCE(ae.label, (ae.raw_data->>'label'))
            ELSE ae.label
        END AS title,
        COALESCE((ae.raw_data->>'source_count')::int, 1) AS source_count,
        COALESCE(
            ARRAY(
                SELECT jsonb_array_elements_text(ae.raw_data->'countries')
            ),
            ARRAY[]::text[]
        ) AS countries,
        COALESCE(
            ae.raw_data->>'outcome_summary',
            ae.raw_data->>'summary',
            ''
        ) AS summary
    FROM analysis_extractions ae
    JOIN assigned a ON ae.id = a.extraction_id
    WHERE ae.extraction_type = p_item_type
    ORDER BY title NULLS LAST;
END;
$$;


CREATE OR REPLACE FUNCTION "public"."get_theme_items_rich"("p_theme_id" "uuid", "p_item_type" "text") RETURNS "jsonb"
    LANGUAGE "plpgsql"
    AS $$
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
$$;


CREATE OR REPLACE FUNCTION "public"."match_chunks"("query_embedding" "public"."vector", "match_threshold" double precision, "match_count" integer, "project_filter" "text" DEFAULT NULL::"text") RETURNS TABLE("id" "uuid", "document_id" "uuid", "content" "text", "similarity" double precision, "chunk_type" "text", "document_title" "text", "document_authors" "jsonb", "top_line" "text")
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  RETURN QUERY
  SELECT
    c.id,
    c.document_id,
    c.content,
    1 - (c.embedding <=> query_embedding) AS similarity,
    c.chunk_type,
    ad.title AS document_title,
    ad.authors AS document_authors,
    ad.top_line AS top_line
  FROM chunks c
  JOIN analysis_documents ad ON c.document_id = ad.id
  WHERE 
    (project_filter IS NULL OR c.project_id = project_filter)
    AND 1 - (c.embedding <=> query_embedding) > match_threshold
  ORDER BY c.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;


CREATE OR REPLACE FUNCTION "public"."update_updated_at_column"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

-- ============================================================================
-- TABLES
-- ============================================================================

CREATE TABLE IF NOT EXISTS "public"."analysis_projects" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "run_id" character varying(24),
    "title" character varying(255) NOT NULL,
    "description" "text",
    "query" "text",
    "total_references" integer DEFAULT 0,
    "relevant_references" integer DEFAULT 0,
    "status" character varying(20) DEFAULT 'created'::character varying,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "created_by_user_id" "text",
    "created_by_name" "text",
    "user_feedback" "jsonb",
    "search_query" "jsonb",
    CONSTRAINT "analysis_projects_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "analysis_projects_run_id_key" UNIQUE ("run_id")
);

COMMENT ON COLUMN "public"."analysis_projects"."created_by_user_id" IS 'Clerk user ID of the person who created this project';
COMMENT ON COLUMN "public"."analysis_projects"."created_by_name" IS 'Display name of the person who created this project (first name + last name or email fallback)';
COMMENT ON COLUMN "public"."analysis_projects"."user_feedback" IS 'User feedback stored as JSON with structure: {"rating": 1-5, "comment": "text", "updated_at": "timestamp", "user_id": "string"}';
COMMENT ON COLUMN "public"."analysis_projects"."search_query" IS 'JSON object containing the complete search plan including original query, boolean query, filters, and search parameters';


CREATE TABLE IF NOT EXISTS "public"."analysis_documents" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "analysis_project_id" "uuid",
    "doc_id" character varying(255) NOT NULL,
    "source" character varying(50) NOT NULL,
    "title" "text",
    "abstract_or_summary" "text",
    "year" integer,
    "is_relevant" boolean,
    "extraction_status" character varying(20),
    "extraction_results" "jsonb",
    "user_feedback_ok" boolean,
    "user_feedback_text" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "authors" "jsonb",
    "doi" "text",
    "source_id" "text",
    "landing_page_url" "text",
    "pdf_url" "text",
    "is_oa" boolean,
    "document_type" "text",
    "document_type_reason" "text",
    "author_institution_countries" "jsonb",
    "relevance_confidence" real,
    "relevance_reason" "text",
    "top_line" "text",
    "acquisition_status" "text",
    "acquisition_error" "text",
    "full_text_available" boolean,
    "file_path" "text",
    "extraction_error" "text",
    "text_source" "text",
    "citation_count" integer,
    "venue" "text",
    "topics" "jsonb",
    "source_country" "text",
    "source_type" "text",
    "published_on" "text",
    "overton_url" "text",
    "upload_step" "text" DEFAULT 'initial'::"text",
    "evidence_category" "text",
    "evidence_confidence" numeric,
    "evidence_category_reasoning" "text",
    CONSTRAINT "analysis_documents_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "analysis_documents_evidence_confidence_check" CHECK ((("evidence_confidence" >= 0.0) AND ("evidence_confidence" <= 1.0)))
);

COMMENT ON COLUMN "public"."analysis_documents"."authors" IS 'JSON array of author names';
COMMENT ON COLUMN "public"."analysis_documents"."author_institution_countries" IS 'JSON array of countries from author institutions';
COMMENT ON COLUMN "public"."analysis_documents"."topics" IS 'JSON array of topic classifications';
COMMENT ON COLUMN "public"."analysis_documents"."upload_step" IS 'Tracks the stage of data upload: initial, screened, acquired, extracted, completed';
COMMENT ON COLUMN "public"."analysis_documents"."evidence_category" IS 'Categorisation of evidence type into 1 of 9 categories';
COMMENT ON COLUMN "public"."analysis_documents"."evidence_confidence" IS 'confidence LLM has in evidence categorisation';
COMMENT ON COLUMN "public"."analysis_documents"."evidence_category_reasoning" IS 'brief rationale produced by LLM as to why a certain evidence type was chosen';


CREATE TABLE IF NOT EXISTS "public"."analysis_extractions" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "analysis_project_id" "uuid",
    "analysis_document_id" "uuid",
    "extraction_type" character varying(20) NOT NULL,
    "label" "text",
    "description" "text",
    "supporting_quote" "text",
    "raw_data" "jsonb",
    "user_feedback_ok" boolean,
    "user_feedback_text" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "analysis_extractions_pkey" PRIMARY KEY ("id")
);


CREATE TABLE IF NOT EXISTS "public"."chunks" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "document_id" "uuid",
    "project_id" "text" NOT NULL,
    "content" "text" NOT NULL,
    "chunk_type" "text" DEFAULT 'summary'::"text",
    "embedding" "public"."vector"(1536),
    "token_count" integer,
    "chunk_index" integer DEFAULT 0,
    "metadata" "jsonb" DEFAULT '{}'::"jsonb",
    "created_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "chunks_pkey" PRIMARY KEY ("id")
);

COMMENT ON COLUMN "public"."chunks"."document_id" IS 'References analysis_documents.id (UUID) for analysis projects, or documents.id for legacy projects';


CREATE TABLE IF NOT EXISTS "public"."synthesis_runs" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "analysis_project_id" "uuid" NOT NULL,
    "status" "text" NOT NULL,
    "version" integer DEFAULT 1 NOT NULL,
    "executive_briefing" "text",
    "model_info" "jsonb",
    "state_after_clustering" "jsonb",
    "state_after_critique" "jsonb",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "evidence_coverage" "jsonb",
    "structured_briefing_data" "jsonb",
    "total_outcomes" integer DEFAULT 0,
    CONSTRAINT "synthesis_runs_pkey" PRIMARY KEY ("id")
);

COMMENT ON COLUMN "public"."synthesis_runs"."evidence_coverage" IS 'Deterministically computed evidence coverage statistics: study_types, countries, years, gaps';
COMMENT ON COLUMN "public"."synthesis_runs"."structured_briefing_data" IS 'Complete structured payload used to generate the executive briefing (for debugging/audit)';
COMMENT ON COLUMN "public"."synthesis_runs"."total_outcomes" IS 'Number of outcome themes discovered in this run';


CREATE TABLE IF NOT EXISTS "public"."synthesis_themes" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "synthesis_run_id" "uuid" NOT NULL,
    "theme_type" "text" NOT NULL,
    "theme_name" "text" NOT NULL,
    "summary_description" "text",
    "impact_summary" "text",
    "frequency" integer DEFAULT 0 NOT NULL,
    "source_doc_ids" "text"[] DEFAULT '{}'::"text"[] NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "impact_snapshot" "text",
    "implementation_context" "text",
    "effect_consensus" character varying(20),
    "positive_count" integer DEFAULT 0,
    "negative_count" integer DEFAULT 0,
    "null_count" integer DEFAULT 0,
    "sample_effect_sizes" "text"[],
    "countries" "text"[],
    "study_types" "jsonb",
    "citation_keys" "text"[],
    "related_outcome_theme_ids" "uuid"[],
    "source_document_ids" "uuid"[],
    CONSTRAINT "synthesis_themes_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "synthesis_themes_theme_type_check" CHECK (("theme_type" = ANY (ARRAY['issue'::"text", 'intervention'::"text", 'result'::"text"])))
);

COMMENT ON COLUMN "public"."synthesis_themes"."impact_snapshot" IS 'Quantitative impact summary, e.g., "~2% reduction in obesity prevalence over 5 years"';
COMMENT ON COLUMN "public"."synthesis_themes"."implementation_context" IS 'Implementation details, e.g., "UK (Proposal). Large OOH businesses (250+ employees)"';
COMMENT ON COLUMN "public"."synthesis_themes"."effect_consensus" IS 'Aggregated effect direction: positive, negative, mixed, null, or insufficient';
COMMENT ON COLUMN "public"."synthesis_themes"."positive_count" IS 'Number of results showing positive/increase effect direction';
COMMENT ON COLUMN "public"."synthesis_themes"."sample_effect_sizes" IS 'Array of representative effect size strings from the evidence';
COMMENT ON COLUMN "public"."synthesis_themes"."countries" IS 'List of countries where evidence for this theme originates';
COMMENT ON COLUMN "public"."synthesis_themes"."study_types" IS 'Distribution of study types, e.g., {"RCT": 3, "case_study": 5, "systematic_review": 1}';
COMMENT ON COLUMN "public"."synthesis_themes"."citation_keys" IS 'Array of citation keys for documents supporting this theme, e.g., ["[Source 1]", "[Smith, 2023]"]';
COMMENT ON COLUMN "public"."synthesis_themes"."related_outcome_theme_ids" IS 'Links intervention themes to their measured outcome themes';
COMMENT ON COLUMN "public"."synthesis_themes"."source_document_ids" IS 'UUIDs of analysis_documents supporting this theme (more reliable than string doc_ids)';


CREATE TABLE IF NOT EXISTS "public"."theme_assignments" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "synthesis_run_id" "uuid" NOT NULL,
    "synthesis_theme_id" "uuid" NOT NULL,
    "extraction_id" "uuid" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "theme_assignments_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "theme_assignments_synthesis_theme_id_extraction_id_key" UNIQUE ("synthesis_theme_id", "extraction_id")
);


CREATE TABLE IF NOT EXISTS "public"."synthesis_citations" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "synthesis_run_id" "uuid" NOT NULL,
    "analysis_document_id" "uuid" NOT NULL,
    "citation_key" "text" NOT NULL,
    "citation_index" integer,
    "author_short" "text",
    "year" integer,
    "title" "text",
    "url" "text",
    "study_type" "text",
    "country" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "supporting_quote" "text",
    "chunk_id" "text",
    "section" character varying(50),
    "claim_text" "text",
    "confidence" double precision DEFAULT 1.0,
    CONSTRAINT "synthesis_citations_pkey" PRIMARY KEY ("id")
);

COMMENT ON TABLE "public"."synthesis_citations" IS 'Stable citation keys for documents, enabling per-claim citations in briefings';
COMMENT ON COLUMN "public"."synthesis_citations"."citation_key" IS 'Display key like "[Smith, 2023]" or "[Source 1]" used in executive briefing';
COMMENT ON COLUMN "public"."synthesis_citations"."supporting_quote" IS 'The exact quote from the source document that supports the claim';
COMMENT ON COLUMN "public"."synthesis_citations"."chunk_id" IS 'Reference to the RCS chunk containing the supporting evidence';
COMMENT ON COLUMN "public"."synthesis_citations"."section" IS 'Briefing section where this citation appears: background, core_answer, interventions, recommendations';
COMMENT ON COLUMN "public"."synthesis_citations"."claim_text" IS 'The specific claim/sentence being supported by this citation usage';
COMMENT ON COLUMN "public"."synthesis_citations"."confidence" IS 'Confidence score (0-1) for quote extraction accuracy';


CREATE TABLE IF NOT EXISTS "public"."synthesis_outcome_themes" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "synthesis_run_id" "uuid" NOT NULL,
    "outcome_name" "text" NOT NULL,
    "outcome_description" "text",
    "effect_consensus" character varying(20),
    "positive_count" integer DEFAULT 0,
    "negative_count" integer DEFAULT 0,
    "null_count" integer DEFAULT 0,
    "sample_effect_sizes" "text"[],
    "frequency" integer DEFAULT 0,
    "source_doc_ids" "text"[],
    "created_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "synthesis_outcome_themes_pkey" PRIMARY KEY ("id")
);

COMMENT ON TABLE "public"."synthesis_outcome_themes" IS 'Clusters semantically similar outcomes (e.g., "obesity reduction", "lower BMI") into canonical themes';
COMMENT ON COLUMN "public"."synthesis_outcome_themes"."effect_consensus" IS 'Aggregated effect direction: positive if mostly increases, negative if mostly decreases, mixed if balanced';


CREATE TABLE IF NOT EXISTS "public"."outcome_theme_assignments" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "synthesis_run_id" "uuid" NOT NULL,
    "synthesis_outcome_theme_id" "uuid" NOT NULL,
    "extraction_id" "uuid" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "outcome_theme_assignments_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "outcome_theme_assignments_synthesis_outcome_theme_id_extrac_key" UNIQUE ("synthesis_outcome_theme_id", "extraction_id")
);

COMMENT ON TABLE "public"."outcome_theme_assignments" IS 'Maps result extractions to their canonical outcome themes';


CREATE TABLE IF NOT EXISTS "public"."user_feedback" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "project_id" "uuid",
    "user_id" "text",
    "user_email" "text",
    "user_name" "text",
    "rating" integer NOT NULL,
    "comment" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "user_feedback_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "user_feedback_rating_check" CHECK ((("rating" >= 1) AND ("rating" <= 5)))
);

COMMENT ON COLUMN "public"."user_feedback"."user_id" IS 'Clerk user ID (text, not uuid)';

-- ============================================================================
-- INDEXES
-- ============================================================================

CREATE INDEX IF NOT EXISTS "chunks_embedding_idx" ON "public"."chunks" USING "ivfflat" ("embedding" "public"."vector_cosine_ops") WITH ("lists"='100');
CREATE INDEX IF NOT EXISTS "chunks_project_id_idx" ON "public"."chunks" USING "btree" ("project_id");
CREATE INDEX IF NOT EXISTS "idx_analysis_documents_acquisition_status" ON "public"."analysis_documents" USING "btree" ("acquisition_status");
CREATE INDEX IF NOT EXISTS "idx_analysis_documents_evidence_category" ON "public"."analysis_documents" USING "btree" ("evidence_category");
CREATE INDEX IF NOT EXISTS "idx_analysis_documents_extraction_status" ON "public"."analysis_documents" USING "btree" ("extraction_status");
CREATE INDEX IF NOT EXISTS "idx_analysis_documents_is_relevant" ON "public"."analysis_documents" USING "btree" ("is_relevant");
CREATE INDEX IF NOT EXISTS "idx_analysis_documents_project" ON "public"."analysis_documents" USING "btree" ("analysis_project_id");
CREATE INDEX IF NOT EXISTS "idx_analysis_documents_relevance" ON "public"."analysis_documents" USING "btree" ("is_relevant");
CREATE INDEX IF NOT EXISTS "idx_analysis_documents_source_country" ON "public"."analysis_documents" USING "btree" ("source_country");
CREATE INDEX IF NOT EXISTS "idx_analysis_documents_source_type" ON "public"."analysis_documents" USING "btree" ("source_type");
CREATE UNIQUE INDEX IF NOT EXISTS "idx_analysis_documents_unique" ON "public"."analysis_documents" USING "btree" ("analysis_project_id", "doc_id", "source") WHERE ("upload_step" <> 'deleted'::"text");
CREATE INDEX IF NOT EXISTS "idx_analysis_documents_upload_step" ON "public"."analysis_documents" USING "btree" ("upload_step");
CREATE INDEX IF NOT EXISTS "idx_analysis_documents_year" ON "public"."analysis_documents" USING "btree" ("year");
CREATE INDEX IF NOT EXISTS "idx_analysis_extractions_document" ON "public"."analysis_extractions" USING "btree" ("analysis_document_id");
CREATE INDEX IF NOT EXISTS "idx_analysis_extractions_type" ON "public"."analysis_extractions" USING "btree" ("extraction_type");
CREATE INDEX IF NOT EXISTS "idx_analysis_projects_user_feedback" ON "public"."analysis_projects" USING "gin" ("user_feedback");
CREATE INDEX IF NOT EXISTS "idx_analysis_projects_user_id" ON "public"."analysis_projects" USING "btree" ("created_by_user_id");
CREATE INDEX IF NOT EXISTS "idx_chunks_document_id" ON "public"."chunks" USING "btree" ("document_id");
CREATE INDEX IF NOT EXISTS "idx_chunks_project_id" ON "public"."chunks" USING "btree" ("project_id");
CREATE INDEX IF NOT EXISTS "idx_citations_document" ON "public"."synthesis_citations" USING "btree" ("analysis_document_id");
CREATE INDEX IF NOT EXISTS "idx_citations_key" ON "public"."synthesis_citations" USING "btree" ("citation_key");
CREATE INDEX IF NOT EXISTS "idx_citations_run" ON "public"."synthesis_citations" USING "btree" ("synthesis_run_id");
CREATE INDEX IF NOT EXISTS "idx_citations_run_number_section" ON "public"."synthesis_citations" USING "btree" ("synthesis_run_id", "citation_index", "section");
CREATE INDEX IF NOT EXISTS "idx_citations_run_section" ON "public"."synthesis_citations" USING "btree" ("synthesis_run_id", "section");
CREATE INDEX IF NOT EXISTS "idx_outcome_assignments_extraction" ON "public"."outcome_theme_assignments" USING "btree" ("extraction_id");
CREATE INDEX IF NOT EXISTS "idx_outcome_assignments_theme" ON "public"."outcome_theme_assignments" USING "btree" ("synthesis_outcome_theme_id");
CREATE INDEX IF NOT EXISTS "idx_outcome_themes_consensus" ON "public"."synthesis_outcome_themes" USING "btree" ("effect_consensus");
CREATE INDEX IF NOT EXISTS "idx_outcome_themes_run" ON "public"."synthesis_outcome_themes" USING "btree" ("synthesis_run_id");
CREATE INDEX IF NOT EXISTS "idx_synthesis_runs_created" ON "public"."synthesis_runs" USING "btree" ("created_at");
CREATE INDEX IF NOT EXISTS "idx_synthesis_runs_project" ON "public"."synthesis_runs" USING "btree" ("analysis_project_id");
CREATE INDEX IF NOT EXISTS "idx_synthesis_themes_run" ON "public"."synthesis_themes" USING "btree" ("synthesis_run_id");
CREATE INDEX IF NOT EXISTS "idx_synthesis_themes_type" ON "public"."synthesis_themes" USING "btree" ("theme_type");
CREATE INDEX IF NOT EXISTS "idx_theme_assignments_extraction" ON "public"."theme_assignments" USING "btree" ("extraction_id");
CREATE INDEX IF NOT EXISTS "idx_theme_assignments_run" ON "public"."theme_assignments" USING "btree" ("synthesis_run_id");
CREATE INDEX IF NOT EXISTS "idx_theme_assignments_theme" ON "public"."theme_assignments" USING "btree" ("synthesis_theme_id");
CREATE INDEX IF NOT EXISTS "idx_themes_effect_consensus" ON "public"."synthesis_themes" USING "btree" ("effect_consensus") WHERE ("effect_consensus" IS NOT NULL);
CREATE INDEX IF NOT EXISTS "idx_user_feedback_project_id" ON "public"."user_feedback" USING "btree" ("project_id");
CREATE INDEX IF NOT EXISTS "idx_user_feedback_user_id" ON "public"."user_feedback" USING "btree" ("user_id");
CREATE UNIQUE INDEX IF NOT EXISTS "uniq_synthesis_runs_project" ON "public"."synthesis_runs" USING "btree" ("analysis_project_id");

-- ============================================================================
-- FOREIGN KEYS
-- ============================================================================

ALTER TABLE "public"."analysis_documents"
    ADD CONSTRAINT "analysis_documents_analysis_project_id_fkey" 
    FOREIGN KEY ("analysis_project_id") REFERENCES "public"."analysis_projects"("id") ON DELETE CASCADE;

ALTER TABLE "public"."analysis_extractions"
    ADD CONSTRAINT "analysis_extractions_analysis_document_id_fkey" 
    FOREIGN KEY ("analysis_document_id") REFERENCES "public"."analysis_documents"("id") ON DELETE CASCADE;

ALTER TABLE "public"."analysis_extractions"
    ADD CONSTRAINT "analysis_extractions_analysis_project_id_fkey" 
    FOREIGN KEY ("analysis_project_id") REFERENCES "public"."analysis_projects"("id") ON DELETE CASCADE;

ALTER TABLE "public"."synthesis_citations"
    ADD CONSTRAINT "fk_citations_document" 
    FOREIGN KEY ("analysis_document_id") REFERENCES "public"."analysis_documents"("id") ON DELETE CASCADE;

ALTER TABLE "public"."synthesis_citations"
    ADD CONSTRAINT "fk_citations_run" 
    FOREIGN KEY ("synthesis_run_id") REFERENCES "public"."synthesis_runs"("id") ON DELETE CASCADE;

ALTER TABLE "public"."outcome_theme_assignments"
    ADD CONSTRAINT "fk_outcome_assignment_extraction" 
    FOREIGN KEY ("extraction_id") REFERENCES "public"."analysis_extractions"("id") ON DELETE CASCADE;

ALTER TABLE "public"."outcome_theme_assignments"
    ADD CONSTRAINT "fk_outcome_assignment_run" 
    FOREIGN KEY ("synthesis_run_id") REFERENCES "public"."synthesis_runs"("id") ON DELETE CASCADE;

ALTER TABLE "public"."outcome_theme_assignments"
    ADD CONSTRAINT "fk_outcome_assignment_theme" 
    FOREIGN KEY ("synthesis_outcome_theme_id") REFERENCES "public"."synthesis_outcome_themes"("id") ON DELETE CASCADE;

ALTER TABLE "public"."synthesis_outcome_themes"
    ADD CONSTRAINT "fk_outcome_themes_run" 
    FOREIGN KEY ("synthesis_run_id") REFERENCES "public"."synthesis_runs"("id") ON DELETE CASCADE;

ALTER TABLE "public"."synthesis_runs"
    ADD CONSTRAINT "synthesis_runs_analysis_project_id_fkey" 
    FOREIGN KEY ("analysis_project_id") REFERENCES "public"."analysis_projects"("id") ON DELETE CASCADE;

ALTER TABLE "public"."synthesis_themes"
    ADD CONSTRAINT "synthesis_themes_synthesis_run_id_fkey" 
    FOREIGN KEY ("synthesis_run_id") REFERENCES "public"."synthesis_runs"("id") ON DELETE CASCADE;

ALTER TABLE "public"."theme_assignments"
    ADD CONSTRAINT "theme_assignments_extraction_id_fkey" 
    FOREIGN KEY ("extraction_id") REFERENCES "public"."analysis_extractions"("id") ON DELETE CASCADE;

ALTER TABLE "public"."theme_assignments"
    ADD CONSTRAINT "theme_assignments_synthesis_run_id_fkey" 
    FOREIGN KEY ("synthesis_run_id") REFERENCES "public"."synthesis_runs"("id") ON DELETE CASCADE;

ALTER TABLE "public"."theme_assignments"
    ADD CONSTRAINT "theme_assignments_synthesis_theme_id_fkey" 
    FOREIGN KEY ("synthesis_theme_id") REFERENCES "public"."synthesis_themes"("id") ON DELETE CASCADE;

ALTER TABLE "public"."user_feedback"
    ADD CONSTRAINT "user_feedback_project_id_fkey" 
    FOREIGN KEY ("project_id") REFERENCES "public"."analysis_projects"("id") ON DELETE CASCADE;

-- ============================================================================
-- ROW LEVEL SECURITY
-- ============================================================================

ALTER TABLE "public"."analysis_documents" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."analysis_extractions" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."analysis_projects" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."chunks" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."outcome_theme_assignments" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."synthesis_citations" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."synthesis_outcome_themes" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."synthesis_runs" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."synthesis_themes" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."theme_assignments" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."user_feedback" ENABLE ROW LEVEL SECURITY;

-- RLS Policies (permissive "Allow all" for now - can be tightened later)
CREATE POLICY "Allow all" ON "public"."analysis_documents" USING (true);
CREATE POLICY "Allow all" ON "public"."analysis_extractions" USING (true);
CREATE POLICY "Allow all" ON "public"."analysis_projects" USING (true);
CREATE POLICY "Allow all operations on outcome_theme_assignments" ON "public"."outcome_theme_assignments" USING (true);
CREATE POLICY "Allow all operations on synthesis_citations" ON "public"."synthesis_citations" USING (true);
CREATE POLICY "Allow all operations on synthesis_outcome_themes" ON "public"."synthesis_outcome_themes" USING (true);

