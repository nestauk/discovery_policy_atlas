## Migrations (squashed)

- `0001_core_analysis.sql`: analysis_projects, analysis_documents, analysis_extractions, user_feedback; includes comments, indexes, and filtered unique index for documents.
- `0002_vector_store_and_match.sql`: pgvector extension, document_chunks table, and match_chunks function.
- `0003_synthesis_and_outcomes.sql`: synthesis runs, claim-level citations, themes, outcome tables, and related indexes/comments.
- `0004_functions_and_helpers.sql`: helper functions (theme items, citation key, outcome themes, evidence coverage). Note: get_theme_items_rich depends on an existing theme_assignments table.

Apply in order.

