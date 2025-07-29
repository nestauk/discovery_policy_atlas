# Installation Guide

This guide will walk you through setting up the Policy Atlas development environment.

## Prerequisites

Before you begin, ensure you have the following installed:

- **Node.js** (v18 or higher)
- **Python** (v3.10 or higher)
- **uv** - Python package manager ([install instructions](https://github.com/astral-sh/uv))
- **Git** - Version control

## Step 1: Clone the Repository

```bash
git clone https://github.com/yourusername/discovery_policy_atlas.git
cd discovery_policy_atlas
```

## Step 2: Frontend Setup

### Install Dependencies

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install --legacy-peer-deps
```

### Environment Configuration

```bash
# Create environment file
cp .env.example .env.local

# Generate auth secret
openssl rand -base64 32
# Copy the output and add it to .env.local as AUTH_SECRET
```

Your `.env.local` should look like:

```env
AUTH_SECRET=your-generated-secret-here
NEXTAUTH_URL=http://localhost:3000
```

## Step 3: Backend Setup

### Install Dependencies

```bash
# Open a new terminal and navigate to backend directory
cd backend

# Install dependencies using uv
uv sync
```

### Environment Configuration

```bash
# Create environment file
cp .env.example .env
```

Your `.env` should contain:

```env
OPENALEX_EMAIL=your-email@example.com  # Optional but recommended by OpenAlex
```

## Step 4: Database Setup

### Install PostgreSQL

**macOS (using Homebrew):**
```bash
brew install postgresql
brew services start postgresql
```

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

**Windows:**
Download and install from [PostgreSQL official website](https://www.postgresql.org/download/windows/)

### Create Database

```bash
# Connect to PostgreSQL
psql -U postgres

# Create database
CREATE DATABASE policy_atlas;

# Create user (optional)
CREATE USER policy_atlas_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE policy_atlas TO policy_atlas_user;

# Exit PostgreSQL
\q
```

### Run Migrations

```bash
cd backend

# Run database migrations
uv run alembic upgrade head
```

## Step 5: Pre-commit Hooks Setup

The project uses pre-commit hooks to ensure code quality:

```bash
# Navigate to backend directory
cd backend

# Install dev dependencies (includes pre-commit)
uv sync --dev

# Install the git hooks
uv run pre-commit install

# Check all files
uv run pre-commit run --all-files
```

## Step 6: Verify Installation

### Start the Backend

```bash
cd backend
uv run python main.py
```

The backend will run on `http://localhost:8000`
API docs available at `http://localhost:8000/docs`

### Start the Frontend

In a new terminal:

```bash
cd frontend
npm run dev
```

The frontend will run on `http://localhost:3000`

### Test the Application

1. Open `http://localhost:3000` in your browser
2. Log in with test credentials:
   - Email: `test@example.com`
   - Password: `password123`
3. Navigate to the Search tab
4. Try searching for "heat pumps" or any academic topic

## Troubleshooting

### Common Issues

**Port Already in Use:**
```bash
# Check what's using the port
lsof -i :8000  # for backend
lsof -i :3000  # for frontend

# Kill the process
kill -9 <PID>
```

**Database Connection Issues:**
- Ensure PostgreSQL is running
- Check database credentials in `.env`
- Verify database exists

**Frontend Build Issues:**
```bash
# Clear node modules and reinstall
rm -rf node_modules package-lock.json
npm install --legacy-peer-deps
```

**Backend Import Issues:**
```bash
# Ensure you're in the virtual environment
uv run python -c "import sys; print(sys.executable)"
```

### Getting Help

If you encounter issues:

1. Check the [Troubleshooting Guide](troubleshooting.md)
2. Search existing [GitHub Issues](https://github.com/yourusername/discovery_policy_atlas/issues)
3. Create a new issue with detailed error information

## Next Steps

Now that you have the development environment set up:

1. Read the [Configuration Guide](configuration.md) to customize your setup
2. Explore the [API Reference](../backend/api-reference.md) to understand the backend
3. Check out the [Frontend Guide](../frontend/overview.md) to understand the React components
4. Review the [Contributing Guide](../development/contributing.md) to start contributing 