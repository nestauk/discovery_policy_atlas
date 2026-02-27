-- db/pgjwt_tle.sql
-- Install pgjwt via Trusted Language Extensions (TLE) on RDS PostgreSQL.
--
-- RDS does not ship pgjwt as a native extension, so we register it through
-- pg_tle (which must be in shared_preload_libraries on the RDS parameter group).
--
-- Idempotent: the DO block skips installation if pgjwt is already registered.
-- Must run BEFORE roles.sql, which does: CREATE EXTENSION pgjwt

CREATE EXTENSION IF NOT EXISTS pg_tle;

DO $outer$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pgtle.available_extensions() WHERE name = 'pgjwt') THEN
    PERFORM pgtle.install_extension(
      'pgjwt',
      '0.2.0',
      'JSON Web Tokens for PostgreSQL',
      $pgjwt$
        CREATE OR REPLACE FUNCTION url_encode(data bytea) RETURNS text
          LANGUAGE sql IMMUTABLE AS $$
            SELECT translate(encode(data, 'base64'), E'+/=\n', '-_');
          $$;

        CREATE OR REPLACE FUNCTION url_decode(data text) RETURNS bytea
          LANGUAGE sql IMMUTABLE AS $$
            WITH t   AS (SELECT translate(data, '-_', '+/')),
                 rem AS (SELECT length((SELECT * FROM t)) % 4)
            SELECT decode(
              (SELECT * FROM t) ||
              CASE WHEN (SELECT * FROM rem) > 0
                   THEN repeat('=', (4 - (SELECT * FROM rem)))
                   ELSE '' END,
              'base64');
          $$;

        CREATE OR REPLACE FUNCTION algorithm_sign(signables text, secret text, algorithm text)
          RETURNS text LANGUAGE sql IMMUTABLE AS $$
            WITH alg AS (
              SELECT CASE
                WHEN algorithm = 'HS256' THEN 'sha256'
                WHEN algorithm = 'HS384' THEN 'sha384'
                WHEN algorithm = 'HS512' THEN 'sha512'
                ELSE '' END AS id
            )
            SELECT url_encode(hmac(signables, secret, (SELECT id FROM alg)));
          $$;

        CREATE OR REPLACE FUNCTION sign(payload json, secret text, algorithm text DEFAULT 'HS256')
          RETURNS text LANGUAGE sql IMMUTABLE AS $$
            WITH
              header    AS (SELECT url_encode(convert_to('{"alg":"' || algorithm || '","typ":"JWT"}', 'utf8')) AS data),
              payload   AS (SELECT url_encode(convert_to(payload::text, 'utf8')) AS data),
              signables AS (SELECT (SELECT data FROM header) || '.' || (SELECT data FROM payload) AS data)
            SELECT
              (SELECT data FROM signables) || '.' ||
              algorithm_sign((SELECT data FROM signables), secret, algorithm);
          $$;

        CREATE OR REPLACE FUNCTION verify(token text, secret text, algorithm text DEFAULT 'HS256')
          RETURNS TABLE(header json, payload json, valid boolean)
          LANGUAGE sql IMMUTABLE AS $$
            SELECT
              convert_from(url_decode(r[1]), 'utf8')::json AS header,
              convert_from(url_decode(r[2]), 'utf8')::json AS payload,
              r[3] = algorithm_sign(r[1] || '.' || r[2], secret, algorithm) AS valid
            FROM regexp_split_to_array(token, '\.') r;
          $$;
      $pgjwt$
    );
  END IF;
END;
$outer$;
