# Clerk → Cognito Migration Runbook

Step-by-step plan for migrating authentication from Clerk to AWS Cognito while
preserving every user's app-owned identity, organisations, and projects.

## Background concepts

- **Provider identity**: the user ID a login provider gives us — Clerk
  (`user_xxx`) or Cognito (`sub`, a UUID).
- **Internal identity**: our own `users.id` (UUID). Stable regardless of
  provider. Owns projects (`analysis_projects.owner_user_id`) and org
  memberships.
- **`user_identities`**: join table mapping `(provider, provider_user_id)` →
  `users.id`. One internal user can have both a `clerk` row and a `cognito`
  row, which is how the same person logs in through either door and lands on
  the same data.
- **`find_or_provision`**: on each authenticated request, resolves the provider
  identity to an internal user, creating one on first sign-in. Email-based
  linking only fires when the provider asserts `email_verified=true`.
- **Cutover**: the moment we flip `AUTH_PROVIDER` from `clerk` to `cognito` and
  deploy. Before: everyone uses Clerk. After: everyone uses Cognito.
- **Two linking strategies**:
  - *Strategy 1 (lazy, runtime)*: `CognitoAuthProvider.enrich()` reads the
    user's verified email via Admin `GetUser`; `find_or_provision` links by
    email. Backstop for real users.
  - *Strategy 2 (deterministic, pre-seed)*: insert `cognito` rows into
    `user_identities` ahead of time using an `email/username → sub` mapping.
    Required for shared/fake-email accounts (which won't link by email).

## Decisions locked in

- Keep both `owner_user_id` (UUID) and legacy `created_by_user_id` (TEXT)
  during transition; no destructive cleanup until after a successful cutover.
- Roles from Clerk are normalised (`org:member` → `member`, `org:admin` →
  `admin`) by the backfill script.
- Migrate the Cognito user pool via **CSV import** for real users (forced
  password reset, `email_verified=true`) and **admin-set passwords** for
  shared/fake-email accounts (e.g. `science_council+clerk_test@nesta.org.uk`).
- Unverified emails are acceptable for the pilot; shared accounts rely on
  Strategy 2, not email linking.
- Cutover happens in **downtime**, so the backfill→cutover gap (projects
  created on Clerk after the backfill snapshot) is a non-issue. Run the
  ownership backfill as the *last* step before flipping.

---

## Phase 0 — Code changes (DONE)

- [x] Identity tables migration (`users`, `user_identities`, `organizations`,
      `organization_memberships`, `analysis_projects.owner_user_id`, updated
      `get_user_projects`).
- [x] `find_or_provision` (auto-provision + email-verified-gated linking,
      cached, off the event loop).
- [x] Backfill script (`backend/scripts/backfill_identities.py`) with role
      normalisation.
- [x] `CognitoAuthProvider.enrich()` — Admin `GetUser` for email/name/
      `email_verified` (cached, graceful degradation).
- [x] IAM grant scaffolding: backend task role gets
      `cognito-idp:AdminGetUser` when `cognito_user_pool_id` is set in
      `infra/pa_config.json` (guarded; no-op while empty).

---

## Staging runbook

### Phase 1 — Get the schema live in staging
- [ ] Open PR, get review, merge `aws_cognito_integration` → `dev`.
- [ ] `deploy-staging.yml` deploys and the migration Lambda applies the new
      migration automatically (CDK copies `backend/supabase/migrations` into
      the Lambda at synth time).
- [ ] In staging Studio, confirm the 4 identity tables and the 6-arg
      `get_user_projects` exist.

### Phase 2 — Pre-flight
- [ ] Confirm the `CLERK_SECRET_KEY` used for the backfill is the **same Clerk
      instance** staging uses (otherwise Clerk IDs won't match staging's
      `created_by_user_id`).
- [ ] Set `cognito_user_pool_id` in `infra/pa_config.json` and redeploy so the
      backend task role gets `AdminGetUser`.
- [ ] Add `COGNITO_REGION` / `COGNITO_USER_POOL_ID` / `COGNITO_APP_CLIENT_ID`
      to the backend container env (keep `AUTH_PROVIDER=clerk` for now).

### Phase 3 — Load Clerk identities into staging
The 4 identity tables are derived purely from Clerk, so they're environment
independent and can be generated locally and uploaded. Project ownership is
env-specific and is done with a SQL UPDATE against staging's own projects.

- [ ] Run the backfill locally with `--commit` (idempotent).
- [ ] Export the identity tables:
      ```bash
      docker compose exec -T postgres pg_dump -U postgres -d policy_atlas \
        --data-only --column-inserts \
        -t users -t user_identities -t organizations -t organization_memberships \
        > identity_seed.sql
      ```
- [ ] Run `identity_seed.sql` in staging Studio's SQL editor (UUIDs carry over).
- [ ] Map ownership against staging's real projects:
      ```sql
      UPDATE analysis_projects ap
      SET owner_user_id = ui.user_id
      FROM user_identities ui
      WHERE ui.provider = 'clerk'
        AND ui.provider_user_id = ap.created_by_user_id
        AND ap.owner_user_id IS NULL;
      ```

### Phase 4 — Spike with ONE account
- [ ] Create one real test user (an email you control) in the Cognito pool,
      `email_verified=true`, forced reset.
- [ ] Pre-seed its `cognito` identity row (single row, Strategy 2).
- [ ] On staging, sign in via Cognito → confirm you land on the existing
      internal user and see its projects/orgs. Proceed only if this works.

### Phase 5 — Populate the Cognito pool (bulk)
- [ ] Real users: CSV bulk import, `email_verified=true`, forced reset.
- [ ] Shared/fake-email users: admin-create with suppressed email + admin-set a
      known shared password.
- [ ] Export the `email/username → cognito sub` mapping.

### Phase 6 — Pre-seed Cognito identities (Strategy 2)
- [ ] Load the mapping in Studio and insert:
      ```sql
      INSERT INTO user_identities (user_id, provider, provider_user_id)
      SELECT u.id, 'cognito', m.cognito_sub
      FROM users u
      JOIN <cognito_mapping> m ON m.email = u.email
      ON CONFLICT (provider, provider_user_id) DO NOTHING;
      ```
- [ ] This is what links the shared/fake-email accounts.

### Phase 7 — Cutover (in downtime)
- [ ] Cognito Managed Login allow-list contains the staging callbacks:
      `${AMPLIFY_APP_ORIGIN}/api/auth/sign-in-callback` and `.../sign-out-callback`.
- [ ] Begin downtime.
- [ ] Re-run the ownership UPDATE (Phase 3 last step) for a fresh snapshot.
- [ ] Backend env: `AUTH_PROVIDER=cognito`. Frontend env:
      `NEXT_PUBLIC_AUTH_PROVIDER=cognito`, `NEXT_PUBLIC_COGNITO_*`,
      `AMPLIFY_APP_ORIGIN`.
- [ ] Deploy. End downtime.

### Phase 8 — Verify & rollback
- [ ] Real user: login → existing projects/orgs visible.
- [ ] Shared account: login with shared password → existing data visible.
- [ ] New user: first login auto-provisions a fresh internal user.
- [ ] `organization_memberships.role` shows `member`/`admin`.
- [ ] **Rollback**: set `AUTH_PROVIDER` back to `clerk` and redeploy. Clerk
      identity rows and `created_by_user_id` are untouched, so nothing is lost.

### Production
Same as staging, triggered by a GitHub release on `main`. `pa_config.json` and
`db_config.json` need a `production` block (currently empty).

---

## Local rehearsal plan

Goal: walk the whole flow on the local docker DB before touching staging.
Cognito is hosted (no local equivalent), so this means **local backend +
frontend + DB authenticating against the real Cognito pool**.

Already done locally: migration applied, Clerk backfill committed (99 users,
6 orgs, 27 memberships), local env points at the real Cognito pool.

### L1 — Seed realistic test data (Clerk-created project)
- [ ] Flip local to Clerk: `AUTH_PROVIDER=clerk` (`backend/.env`) and
      `NEXT_PUBLIC_AUTH_PROVIDER=clerk` (`frontend/.env.local`); restart both.
- [ ] Sign in via Clerk as someone in the backfilled set (note the email).
- [ ] Create a project or two → `created_by_user_id` = Clerk sub,
      `owner_user_id` = NULL.

### L2 — Prove the "missing without backfill" failure (optional but instructive)
- [ ] Flip local back to Cognito; restart.
- [ ] Pre-seed the Cognito identity for that same person (their pool `sub` →
      existing internal UUID).
- [ ] Sign in via Cognito → the project is **missing** (owner_user_id is NULL,
      created_by is the Clerk sub). This demonstrates why the backfill matters.

### L3 — Run the ownership backfill
- [ ] Run the ownership UPDATE against the local DB:
      ```sql
      UPDATE analysis_projects ap
      SET owner_user_id = ui.user_id
      FROM user_identities ui
      WHERE ui.provider = 'clerk'
        AND ui.provider_user_id = ap.created_by_user_id
        AND ap.owner_user_id IS NULL;
      ```
- [ ] Refresh → the project now **appears** under the Cognito login. This is
      the core migration promise, proven locally.

### L4 — Verify identity linking
- [ ] Confirm no duplicate internal user was created for the Cognito sign-in
      (the `cognito` identity points at the same `users.id` as the `clerk` one).
      ```sql
      SELECT ui.provider, ui.provider_user_id, ui.user_id
      FROM user_identities ui
      JOIN users u ON u.id = ui.user_id
      WHERE u.email = '<test email>'
      ORDER BY ui.provider;
      ```

### L5 — Exercise the bulk + shared-account paths (optional)
- [ ] CSV import remaining users into the real pool.
- [ ] Pre-seed all `cognito` identities into the local DB (Phase 6 SQL).
- [ ] Sign in as a shared/fake-email account → verify it resolves via the
      pre-seeded identity (not email).
- [ ] Sign in as a brand-new email → verify a fresh internal user is created.

### Notes for local
- `enrich()` needs AWS creds locally (SSO/keys) with `AdminGetUser` to test
  Strategy 1. Without them it degrades gracefully; Strategy 2 (pre-seed) still
  works because resolution is by `(provider, sub)`, not email.
- Cognito callback allow-list already includes the `localhost:3000` URLs.
- Reset local DB if needed: `docker compose down -v && docker compose up -d`
  (re-applies migrations; re-run the backfill afterwards).
