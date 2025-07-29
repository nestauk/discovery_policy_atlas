# Quick Start Guide

Get Policy Atlas up and running in under 10 minutes! This guide covers the essential steps to start developing.

## Prerequisites

- Node.js (v18+)
- Python (v3.10+)
- uv package manager
- Git

## 🚀 Quick Setup

### 1. Clone and Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/discovery_policy_atlas.git
cd discovery_policy_atlas

# Setup backend
cd backend
uv sync
cp .env.example .env

# Setup frontend
cd ../frontend
npm install --legacy-peer-deps
cp .env.example .env.local
```

### 2. Generate Auth Secret

```bash
# Generate a secret for NextAuth
openssl rand -base64 32
```

Add the output to `frontend/.env.local` as `AUTH_SECRET=your-generated-secret`

### 3. Start the Application

**Terminal 1 - Backend:**
```bash
cd backend
uv run python main.py
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```

### 4. Test It Out

1. Open [http://localhost:3000](http://localhost:3000)
2. Login with: `test@example.com` / `password123`
3. Try searching for "heat pumps"

## 🎯 What You Can Do

### Search Papers
- Query academic databases (OpenAlex, MediaCloud)
- Filter by date, source, and relevance
- Save interesting papers to projects

### AI Synthesis
- Select multiple papers for analysis
- Generate summaries and insights
- Focus on specific policy areas

### Project Management
- Organize research into projects
- Track your analysis progress
- Export findings

## 🔧 Development Workflow

### Backend Development
```bash
cd backend
uv run python main.py  # Start server
uv run pytest          # Run tests
uv run pre-commit run  # Check code quality
```

### Frontend Development
```bash
cd frontend
npm run dev     # Start dev server
npm run build   # Build for production
npm run lint    # Check code quality
```

### Database Changes
```bash
cd backend
uv run alembic revision --autogenerate -m "description"
uv run alembic upgrade head
```

## 📚 Next Steps

- [Full Installation Guide](installation.md) - Detailed setup instructions
- [API Reference](../backend/api-reference.md) - Backend API documentation
- [Frontend Guide](../frontend/overview.md) - React component documentation
- [Contributing Guide](../development/contributing.md) - How to contribute

## 🆘 Need Help?

- Check the [Troubleshooting Guide](troubleshooting.md)
- Open an issue on [GitHub](https://github.com/yourusername/discovery_policy_atlas/issues)
- Join our [Discord/Slack](link-to-community)

---

**Ready to dive deeper?** Check out the [full documentation](../index.md) for comprehensive guides and API references. 