# Installation Guide

This guide will help you set up a local deployment of the Policy Atlas app.

## Prerequisites

Before you begin, ensure you have the following installed:

- **Node.js** (frontend development; [install instructions](https://formulae.brew.sh/formula/node), v18 or higher)
- **uv** (Python package manager; [install instructions](https://github.com/astral-sh/uv))


## Step 1: Clone the repository

```bash
git clone https://github.com/yourusername/discovery_policy_atlas.git
cd discovery_policy_atlas
```

## Step 2: Frontend setup

### Install dependencies

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install --legacy-peer-deps
```

### Environment configuration

Frontend environment file contains keys required for user authentication.

```bash
# Create environment file
cp .env.example .env.local
```

Your `.env.local` should look like:

```env
# Clerk auth
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=
CLERK_SECRET_KEY=
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL=/dashboard
NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL=/dashboard
```

You can run the frontend also without specifying the environment variables, and Clerk will allow you to create a 
user account. This will not be connected to any existing Clerk app.

## Step 3: Backend setup

### Install dependencies

```bash
# Open a new terminal and navigate to backend directory
cd backend

# Install dependencies using uv
uv sync
```

### Environment configuration

```bash
# Create environment file
cp .env.example .env
```

Your `.env` should contain:

```env
# OpenAlex asks for email for polite use (optional but recommended)
OPENALEX_EMAIL=

# Overton API key
OVERTON_API_KEY=

# LLM configuration
LLM_SERVICE=OpenAI
OPENAI_API_KEY=

# Supabase logging (optional)
SUPABASE_URL=
SUPABASE_KEY=

# Clerk auth
CLERK_SECRET_KEY=
CLERK_PUBLISHABLE_KEY=
CLERK_JWT_ISSUER=

# Allowed incoming sources to backend API calls
BACKEND_CORS_ORIGINS = your-app.url,http://localhost:3000

# Development/testing
MOCK_OPENAI=false
```

## Step 4: Database setup

Coming soon! (we haven't implemented a database yet)


## Step 5: Pre-commit hooks setup

The project uses pre-commit hooks to ensure code quality for both frontend and backend. 

Pre-commit runs from the project root and automatically:

- runs Ruff on Python files in the `backend/` directory;
- runs ESLint on TypeScript/JavaScript files in the `frontend/` directory.

### Install pre-commit hooks

```bash
# Navigate to backend directory to install pre-commit
cd backend

# Install dev dependencies (includes pre-commit)
uv sync --dev

# Install the git hooks (must be run from project root)
cd ..
uv run --directory backend pre-commit install

# Test the hooks on all files
uv run --directory backend pre-commit run --all-files
```

### Manual linting (optional)

You can also run linting manually:

```bash
# Frontend linting
cd frontend
npm run lint

# Backend linting  
cd backend
uv run ruff check .
uv run ruff format .
```

## Step 6: Run the app

You'll need two terminal windows.

### Terminal 1: Start the backend

```bash
cd backend
uv run python main.py
```

The backend will run on `http://localhost:8000`
API docs available at `http://localhost:8000/docs` and `http://localhost:8000/redoc`

### Terminal 2: Start the frontend

```bash
cd frontend
npm run dev
```

The frontend will run on `http://localhost:3000`
