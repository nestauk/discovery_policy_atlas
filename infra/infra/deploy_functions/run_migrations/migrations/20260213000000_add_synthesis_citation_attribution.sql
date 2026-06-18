ALTER TABLE "public"."synthesis_citations"
ADD COLUMN IF NOT EXISTS "attribution" character varying(20);

COMMENT ON COLUMN "public"."synthesis_citations"."attribution" IS
'Attribution type for claim support: direct, synthesised, inferred';
