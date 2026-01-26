# User Management

Policy Atlas uses [Clerk](https://clerk.com/) for authentication and organization management. Project access is controlled based on the user's organization membership.

## Architecture

- **Clerk**: Handles user authentication, passwords, and organization assignments
- **Supabase**: Stores project data with `organization_id` for multi-tenancy
- **JWT Claims**: Organization info (`org_id`, `org_slug`) is passed from Clerk to the backend via JWT tokens

## Project access rules

Access is evaluated in priority order—first matching rule wins:

| Priority | Condition | Access |
|----------|-----------|--------|
| 1 | Admin org (`nesta-dev`) | ✅ See all projects |
| 2 | Project creator | ✅ Always see own projects |
| 3 | Demo org project | ✅ Everyone can see |
| 4 | Same org project | ✅ See org's projects |
| - | Otherwise | ❌ No access |

The filtering logic is implemented in the PostgreSQL function `get_user_projects` (see `migrations/20260107000002_add_get_user_projects_function.sql`).

## User experience

### Users with an organization

- Organization name displayed in sidebar under user avatar
- "Show all org projects" toggle available on projects page, to see colleagues' searches
- Default view shows only their created projects

### Users without an organization

- No organization shown in sidebar
- No toggle on projects page
- Only see their own created projects and demo projects

## Configuration

Environment variables:

| Variable | Description |
|----------|-------------|
| `DEMO_ORG_ID` | Clerk organization ID for demo projects (visible to all users) |

The admin org slug (`nesta-dev`) is hardcoded in `backend/app/api/projects.py`.

## Clerk JWT Setup

Ensure Clerk session tokens include these claims (configure in Clerk Dashboard, Configure → Sessions):

```json
{
  "org_id": "{{org.id}}",
  "org_slug": "{{org.slug}}",
  "org_role": "{{org.role}}",
  "email": "{{user.primary_email_address}}",
  "first_name": "{{user.first_name}}",
  "last_name": "{{user.last_name}}"
}
```

## Assigning users to organizations

Currently done manually via Clerk Dashboard:

1. Go to Clerk Dashboard → Organizations
2. Select or create an organization
3. Add users as members
