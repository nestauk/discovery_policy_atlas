# 🌐 Policy Atlas

We're harnessing AI to improve policy design, helping users search, synthesise, and simulate policy interventions.

Find more information [on the website](https://www.nesta.org.uk/project/policy-atlas-harnessing-ai-to-improve-policy-design/).

⚠️ Heavily work-in-progress ⚠️

## 📋 Overview

Policy Atlas is a web application designed to streamline policy evidence exploration. Currently in prototype phase, it provides:

- **Search**: Query academic and policy papers (coming soon)
- **Synthesis**: AI-powered research synthesis across multiple sources (coming soon)
- **Simulation**: Policy outcome modeling based on evidence (coming soon)

## 🛠️ Tech Stack

### Frontend
- **Next.js 14** (App Router) - React framework
- **TypeScript** - Type safety
- **Tailwind CSS** - Styling
- **shadcn/ui** - UI component library
- **NextAuth.js v5** - Authentication

### Backend
- **FastAPI** - Python web framework
- **uv** - Python package manager
- **httpx** - Async HTTP client
- **OpenAlex API** - Academic paper database

## 📦 Prerequisites

Before you begin, ensure you have the following installed:
- **Node.js** (v18 or higher)
- **Python** (v3.10 or higher)
- **uv** - Python package manager ([install instructions](https://github.com/astral-sh/uv))

## 🚀 Setup Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/discovery_policy_atlas.git
cd discovery_policy_atlas
```

### 2. Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install --legacy-peer-deps

# Create environment file
cp .env.example .env.local

# Generate auth secret
openssl rand -base64 32
# Copy the output and add it to .env.local as AUTH_SECRET

# Your .env.local should look like:
# AUTH_SECRET=your-generated-secret-here
# NEXTAUTH_URL=http://localhost:3000
```

### 3. Backend Setup

```bash
# Open a new terminal and navigate to backend directory
cd backend

# Install dependencies using uv
uv sync

# Create environment file
cp .env.example .env

# Your .env should contain:
# OPENALEX_EMAIL=your-email@example.com  # Optional but recommended by OpenAlex
```

### 4. Running the Application

You'll need two terminal windows:

**Terminal 1 - Backend:**
```bash
cd backend
uv run python main.py
# Backend will run on http://localhost:8000
# API docs available at http://localhost:8000/docs
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
# Frontend will run on http://localhost:3000
```

### 5. Test the Application

1. Open http://localhost:3000 in your browser
2. Log in with test credentials:
   - Email: `test@example.com`
   - Password: `password123`
3. Navigate to the Search tab
4. Try searching for "heat pumps" or any academic topic

## 📁 Project Structure

```
discovery_policy_atlas/
│
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI routes (e.g., routes.py)
│   │   ├── core/          # Core models and config (models.py, config.py)
│   │   ├── services/      # Main backend services
│   │   ├── utils/         # Utility modules
│   ├── main.py            
│   └── .venv/             # Python virtual environment
│
├── frontend/
│   ├── app/               # Next.js app directory
│   ├── components/
│   │   ├── search/        # Search-related React components
│   │   ├── ui/            # UI primitives/components
│   ├── types/             # TypeScript types
│   ├── public/            # Static assets
│   ├── lib/               # Frontend utility libraries
│
├── docs/
```

## 📝 Environment Variables

### Frontend (.env.local)
```env
AUTH_SECRET=            # Generate with: openssl rand -base64 32
NEXTAUTH_URL=http://localhost:3000
```

### Backend (.env)
```env
OPENALEX_EMAIL=         # Your email (optional, for OpenAlex politeness)
```

## 🚧 Roadmap (tentative)

- [ ] Database integration (PostgreSQL)
- [ ] Real user authentication
- [ ] Search result screening and synthesis with LLMs
- [ ] PDF processing
- [ ] Deployment to cloud

## 🤝 Contributing

This is currently a prototype. For major changes, please open an issue first to discuss what you would like to change.

## 📄 License

[MIT License](LICENSE)