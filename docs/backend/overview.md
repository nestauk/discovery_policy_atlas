# Backend overview

The Policy Atlas backend is built with **FastAPI**, following a service-oriented architecture with clear separation of concerns.

The API request flow is as follows:
```
Client Request → FastAPI Router → Service Layer → External APIs/Database → Response
```

## Core principles

**Modular design**: Clear separation between API routes, services, and utilities

  - **Routes** handle HTTP concerns - parsing requests, validation, authentication, and formatting responses. They're the entry point but should be thin.
  - **Services** contain the core business logic - the "what" the application does. This includes data processing, business rules, orchestrating multiple operations, and complex workflows.
  - **Utils** provide reusable helper functions that aren't business-specific - date formatting, string manipulation, generic validators, etc.

**Type safety**: Comprehensive Pydantic models for request/response validation

## Structure

```
backend/
│── main.py                         # Application entry point
│
├── alembic/                        # Database migrations (basic setup, placeholder for now)
│   ├── env.py                      # Migration environment config
│   ├── versions/                   # Migration files (placeholder)
│   └── script.py.mako              # Migration template
│
├── app/
│   ├── api/                        # FastAPI routes and endpoints
│   │   ├── __init__.py
│   │   ├── routes.py               # Main API routes
│   │   └── projects.py             # Project management routes
│   │
│   ├── core/                       # Core application components
│   │   ├── auth.py                 # Authentication logic
│   │   ├── config.py               # Application settings
│   │   ├── database.py             # Database connection setup
│   │   └── models.py               # Core data models
│   │
│   ├── models/                     # Database models (maybe rename to database?)
│   │   └── database.py             # SQLAlchemy models (not yet used)
│   │
│   ├── services/                   # Business logic services
│   │   ├── download.py             # File download service
│   │   ├── logging.py              # Supabase logging service
│   │   ├── mediacloud.py           # MediaCloud API integration
│   │   ├── openalex.py             # OpenAlex API integration
│   │   ├── overton.py              # Overton API integration
│   │   ├── screening.py            # AI-powered paper screening
│   │   └── summary.py              # AI summary generation
│   │
│   ├── utils/                      # Utility functions
│   │   └── overton.py              # Overton-specific utilities
│   │
│   └── main.py                     # FastAPI application factory
│
├── Configuration files
│   ├── pyproject.toml              # Dependencies and project config
|   ├── .python-version             # File specifying Python version
│   ├── alembic.ini                 # Database migration config
│   └── Procfile                    # Deployment configuration for Railway (not required?)
│
└── Runtime directories
    ├── exports/                    # Generated export files (not used?)
    ├── logs/                       # Application logs (not used?)
    └── temp/                       # Temporary files
```

Note that the database functionalities are not yet fully implemented, and the correspond files are placeholders.

## Authentication

The backend integrates with **Clerk** for JWT-based authentication. The frontend handles user login/logout through Clerk, and the backend validates JWT tokens on protected routes.

### How it works

1. **Frontend authentication**: Users log in through Clerk on the frontend
2. **JWT token**: Clerk provides a JWT token that's sent with API requests
3. **Backend validation**: The backend validates the JWT token using Clerk's public keys
4. **User context**: Authenticated endpoints receive a `CurrentUser` object with user details

### Implementation (`core/auth.py`)

```python
from fastapi import Depends
from app.core.auth import get_current_user, CurrentUser

@router.post("/api/search")
async def search(
    request: SearchRequest, 
    current_user: CurrentUser = Depends(get_current_user)
):
    # current_user.user_id contains the Clerk user ID
    # current_user.email contains the user's email
    ...
```

### Environment variables

```env
CLERK_JWT_ISSUER=https://your-clerk-domain.clerk.accounts.dev
```

The JWT issuer URL is provided by Clerk and used to validate tokens. The backend automatically constructs the JWKS URL from this issuer to fetch Clerk's public keys for token verification.

### Protected endpoints

All main API endpoints (search, synthesis) require authentication. The `/health` endpoint is public for monitoring purposes.

## Database

We're experimenting with Supabase as a database solution. For example, we're using it to implement logging user search queries.

### Example Schema

```sql
CREATE TABLE searches (
  search_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  search_query TEXT NOT NULL,
  user_id TEXT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

