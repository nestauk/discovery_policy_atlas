#!/usr/bin/env python3
"""One-shot backfill: import Clerk users/orgs into app-owned identity tables.

Reads all users and organisations from the Clerk API, then upserts into:
  - users
  - user_identities  (provider='clerk')
  - organizations
  - organization_memberships

Also backfills ``analysis_projects.owner_user_id`` from the legacy
``created_by_user_id`` column using the newly-created identity links.

Usage:
    # Dry-run (default) — prints what would be written, changes nothing:
    uv run python scripts/backfill_identities.py

    # Actually write to the database:
    uv run python scripts/backfill_identities.py --commit

Required env vars (loaded from .env if present):
    CLERK_SECRET_KEY   — Clerk Backend API secret key
    SUPABASE_URL       — Supabase project URL
    SUPABASE_KEY       — Supabase service-role key (needs write access)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

CLERK_API = "https://api.clerk.com/v1"


def _env(name: str) -> str:
    val = os.getenv(name, "").strip()
    if not val:
        logger.error("Missing required env var: %s", name)
        sys.exit(1)
    return val


def fetch_clerk_paginated(path: str, headers: dict) -> list[dict]:
    """Fetch all pages from a Clerk list endpoint."""
    items: list[dict] = []
    offset = 0
    limit = 100
    while True:
        resp = httpx.get(
            f"{CLERK_API}{path}",
            headers=headers,
            params={"limit": limit, "offset": offset},
        )
        resp.raise_for_status()
        data = resp.json()

        batch = data if isinstance(data, list) else data.get("data", [])
        if not batch:
            break
        items.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Actually write to the database (default is dry-run).",
    )
    args = parser.parse_args()
    dry_run = not args.commit

    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)

    clerk_key = _env("CLERK_SECRET_KEY")
    supabase_url = _env("SUPABASE_URL")
    supabase_key = _env("SUPABASE_KEY")
    headers = {"Authorization": f"Bearer {clerk_key}"}

    supabase = create_client(supabase_url, supabase_key)

    # ------------------------------------------------------------------
    # 1. Fetch Clerk users
    # ------------------------------------------------------------------
    logger.info("Fetching users from Clerk...")
    clerk_users = fetch_clerk_paginated("/users", headers)
    logger.info("Found %d Clerk users", len(clerk_users))

    user_rows = []
    clerk_id_to_internal: dict[str, str] = {}

    for cu in clerk_users:
        clerk_id = cu["id"]
        emails = cu.get("email_addresses", [])
        primary_email_id = cu.get("primary_email_address_id")
        email = None
        for e in emails:
            if e.get("id") == primary_email_id:
                email = e.get("email_address")
                break
        if not email and emails:
            email = emails[0].get("email_address")

        name_parts = [cu.get("first_name", ""), cu.get("last_name", "")]
        name = " ".join(p for p in name_parts if p).strip() or None

        user_rows.append({"email": email, "name": name, "_clerk_id": clerk_id})

    if dry_run:
        logger.info("[DRY RUN] Would upsert %d users", len(user_rows))
        for r in user_rows[:5]:
            logger.info(
                "  user: %s <%s> (clerk: %s)", r["name"], r["email"], r["_clerk_id"]
            )
        if len(user_rows) > 5:
            logger.info("  ... and %d more", len(user_rows) - 5)
    else:
        for row in user_rows:
            clerk_id = row.pop("_clerk_id")
            existing = (
                supabase.table("user_identities")
                .select("user_id")
                .eq("provider", "clerk")
                .eq("provider_user_id", clerk_id)
                .maybe_single()
                .execute()
            )
            if existing and existing.data:
                internal_id = existing.data["user_id"]
                logger.info(
                    "User %s already linked (internal %s)", clerk_id, internal_id
                )
            else:
                user_result = (
                    supabase.table("users")
                    .insert({"email": row["email"], "name": row["name"]})
                    .execute()
                )
                internal_id = user_result.data[0]["id"]
                supabase.table("user_identities").insert(
                    {
                        "user_id": internal_id,
                        "provider": "clerk",
                        "provider_user_id": clerk_id,
                    }
                ).execute()
                logger.info("Created user %s for Clerk %s", internal_id, clerk_id)

            clerk_id_to_internal[clerk_id] = internal_id

    # ------------------------------------------------------------------
    # 2. Fetch Clerk organisations
    # ------------------------------------------------------------------
    logger.info("Fetching organisations from Clerk...")
    clerk_orgs = fetch_clerk_paginated("/organizations", headers)
    logger.info("Found %d Clerk organisations", len(clerk_orgs))

    org_rows = []
    for co in clerk_orgs:
        org_rows.append(
            {
                "name": co["name"],
                "slug": co.get("slug"),
                "external_id": co["id"],
            }
        )

    clerk_org_to_internal: dict[str, str] = {}

    if dry_run:
        logger.info("[DRY RUN] Would upsert %d organisations", len(org_rows))
        for r in org_rows:
            logger.info(
                "  org: %s (slug=%s, clerk=%s)", r["name"], r["slug"], r["external_id"]
            )
    else:
        for row in org_rows:
            existing = (
                supabase.table("organizations")
                .select("id")
                .eq("external_id", row["external_id"])
                .maybe_single()
                .execute()
            )
            if existing and existing.data:
                internal_id = existing.data["id"]
                logger.info(
                    "Org %s already exists (internal %s)",
                    row["external_id"],
                    internal_id,
                )
            else:
                org_result = supabase.table("organizations").insert(row).execute()
                internal_id = org_result.data[0]["id"]
                logger.info(
                    "Created org %s for Clerk %s", internal_id, row["external_id"]
                )

            clerk_org_to_internal[row["external_id"]] = internal_id

    # ------------------------------------------------------------------
    # 3. Fetch Clerk memberships
    # ------------------------------------------------------------------
    membership_count = 0
    for co in clerk_orgs:
        org_clerk_id = co["id"]
        members = fetch_clerk_paginated(
            f"/organizations/{org_clerk_id}/memberships", headers
        )
        for m in members:
            user_clerk_id = m.get("public_user_data", {}).get("user_id")
            role = m.get("role", "member")
            if not user_clerk_id:
                continue
            membership_count += 1

            if dry_run:
                logger.info(
                    "[DRY RUN] Would add membership: user %s -> org %s (role=%s)",
                    user_clerk_id,
                    org_clerk_id,
                    role,
                )
            else:
                internal_user_id = clerk_id_to_internal.get(user_clerk_id)
                internal_org_id = clerk_org_to_internal.get(org_clerk_id)
                if not internal_user_id or not internal_org_id:
                    logger.warning(
                        "Skipping membership — missing mapping for user=%s or org=%s",
                        user_clerk_id,
                        org_clerk_id,
                    )
                    continue
                supabase.table("organization_memberships").upsert(
                    {
                        "user_id": internal_user_id,
                        "organization_id": internal_org_id,
                        "role": role,
                    },
                    on_conflict="user_id,organization_id",
                ).execute()

    logger.info("Processed %d memberships", membership_count)

    # ------------------------------------------------------------------
    # 4. Backfill analysis_projects.owner_user_id
    # ------------------------------------------------------------------
    if dry_run:
        logger.info(
            "[DRY RUN] Would backfill analysis_projects.owner_user_id from user_identities"
        )
    else:
        projects = (
            supabase.table("analysis_projects")
            .select("id, created_by_user_id")
            .is_("owner_user_id", "null")
            .not_.is_("created_by_user_id", "null")
            .execute()
        )
        backfilled = 0
        for p in projects.data:
            internal_id = clerk_id_to_internal.get(p["created_by_user_id"])
            if internal_id:
                supabase.table("analysis_projects").update(
                    {"owner_user_id": internal_id}
                ).eq("id", p["id"]).execute()
                backfilled += 1
        logger.info(
            "Backfilled owner_user_id for %d / %d projects",
            backfilled,
            len(projects.data),
        )

    if dry_run:
        logger.info("DRY RUN complete — no changes made. Use --commit to write.")
    else:
        logger.info("Backfill complete!")


if __name__ == "__main__":
    main()
