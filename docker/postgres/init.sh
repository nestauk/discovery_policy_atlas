#!/bin/sh
set -e

# Apply all migrations in timestamp order.
# The roles migration reads current_setting('app.authenticator_password'),
# so we prepend a SET for every file (harmless for the others).
for f in /migrations/*.sql; do
    echo "Applying $(basename "$f") ..."
    (echo "SET app.authenticator_password = 'authenticator';"; cat "$f") | \
        psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB"
done

echo "All migrations applied."
