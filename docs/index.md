# 🌐 Policy Atlas

Policy Atlas is a web application designed to streamline policy evidence exploration. The app will help policy analysts and researchers to **search** and **synthesise** policy evidence, and **simulate** policy interventions.

This technical documentation will help you understand, set up, and contribute to our AI-powered policy design platform. 

⚠️ This is a work-in-progress and subject to substantial changes in the next few months!

## Tech Stack

### Frontend
- **Next.js 15** - React framework with App Router
- **React 19** - UI library
- **TypeScript** - Type safety
- **Tailwind CSS** - Utility-first CSS framework
- **Clerk** - Authentication and user management
- **shadcn/ui + Ant Design** - UI component libraries
- **Zustand** - Client-side state management

### Backend
- **FastAPI** - Python web framework
- **uv** - Python package manager
- **OpenAlex API** - Academic paper database
- **Overton API** - Grey literature database


## Project Structure

```
discovery_policy_atlas/
├── backend/                   # FastAPI Python backend
│   ├── alembic/               # Database migrations
│   ├── app/
│   │   ├── api/               # API routes and endpoints
│   │   ├── core/              # Core configuration and models
│   │   ├── models/            # Database models
│   │   ├── services/          # Business logic and external integrations
│   │   └── utils/             # Utility functions
│   ├── main.py                # Application entry point
│   └── pyproject.toml         # Python dependencies
│
├── frontend/                  # Next.js React frontend
│   ├── app/                   # Next.js App Router pages
│   ├── components/            # Reusable React components
│   ├── lib/                   # Frontend utilities and API client
│   ├── types/                 # TypeScript type definitions
│   └── package.json           # Node.js dependencies
│
├── docs/                      # Technical documentation
│
└── Configuration files
    ├── docker-compose.yml     # Container orchestration (for databases)
    ├── mkdocs.yml             # Documentation site config
    └── railway.toml           # Deployment configuration (not used?)
```