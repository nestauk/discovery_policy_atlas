# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Policy Atlas is an AI-powered web application for policy research exploration, built with FastAPI backend and Next.js frontend. The project is in heavy work-in-progress/prototype phase with search functionality implemented and synthesis/simulation features coming soon.

## Architecture

- **Backend**: FastAPI Python application using async/await patterns
- **Frontend**: Next.js 15 with TypeScript, Tailwind CSS, and Ant Design components
- **State Management**: Zustand stores for client-side state
- **Authentication**: Clerk for user auth across both frontend/backend
- **Database**: PostgreSQL with SQLAlchemy (work in progress)
- **AI Services**: OpenAI integration via LangChain for document analysis and RAG
- **External APIs**: OpenAlex (academic papers), Overton (policy documents), Media Cloud

## Development Commands

### Backend (Python)
```bash
cd backend

# Install dependencies
uv sync
uv sync --dev  # Include dev dependencies

# Run server
uv run python main.py  # Starts on http://localhost:8000

# Run tests
uv run pytest test/

# Linting
uv run ruff check .
uv run ruff format .
```

### Frontend (Node.js)
```bash
cd frontend

# Install dependencies  
npm install --legacy-peer-deps

# Run dev server
npm run dev  # Starts on http://localhost:3000

# Build and lint
npm run build
npm run lint
```

### Full Stack
```bash
# Start database services
docker-compose up -d

# Pre-commit hooks (from root)
uv run --directory backend pre-commit install
uv run --directory backend pre-commit run --all-files
```

## Key Configuration

- Backend config in `backend/app/core/config.py` with Pydantic settings
- Frontend uses environment variables for Clerk auth and API endpoints
- Both services require environment files (.env for backend, .env.local for frontend)
- CORS configured for localhost:3000 and production domains

## File Structure

- `backend/app/`: FastAPI application
  - `api/`: API routes (search, projects, agent endpoints)
  - `services/`: Core business logic (analysis, RAG, vectorization)
  - `core/`: Configuration, auth, database
- `frontend/app/`: Next.js pages and layouts
  - `dashboard/`: Main app interface 
  - `agent/`: Conversational interface
- `frontend/components/`: Reusable UI components
- `frontend/lib/`: Client utilities and Zustand stores

## Testing

Backend uses pytest with async support. Frontend testing setup not yet implemented.

## Documentation

Technical documentation built with MkDocs Material, available at project GitHub Pages.

## Principles of coding 
Always consider YAGNI + SOLID + KISS + DRY principles when designing or adding new code.