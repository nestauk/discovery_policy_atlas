# 🌐 Policy Atlas Documentation

Welcome to the Policy Atlas documentation! This comprehensive guide will help you understand, set up, and contribute to our AI-powered policy design platform.

## 🎯 What is Policy Atlas?

Policy Atlas is a web application designed to streamline policy evidence exploration. We're harnessing AI to improve policy design, helping users search, synthesise, and simulate policy interventions.

### Key Features

- **🔍 Search**: Query academic and policy papers from multiple sources
- **🧠 Synthesis**: AI-powered research synthesis across multiple sources
- **🎯 Simulation**: Policy outcome modeling based on evidence
- **📊 Analysis**: Advanced screening and analysis tools

## 🚀 Quick Start

1. **[Installation](getting-started/installation.md)** - Set up your development environment
2. **[Configuration](getting-started/configuration.md)** - Configure the application
3. **[API Reference](backend/api-reference.md)** - Explore the backend API
4. **[Interactive API Docs](http://localhost:8000/docs)** - Test endpoints directly in your browser
5. **[Frontend Guide](frontend/overview.md)** - Understand the React/Next.js frontend

## 🏗️ Architecture

Policy Atlas consists of two main components:

### Backend (FastAPI)
- **API Layer**: RESTful endpoints for data access
- **Services**: Core business logic and external API integrations
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Authentication**: JWT-based authentication system

### Frontend (Next.js)
- **Pages**: Next.js App Router for routing
- **Components**: Reusable React components with shadcn/ui
- **State Management**: Client-side state with React hooks
- **Authentication**: NextAuth.js integration

## 📚 Documentation Sections

### Getting Started
- [Quick Start](getting-started/quick-start.md) - Get up and running in minutes
- [Installation](getting-started/installation.md) - Detailed setup instructions
- [Configuration](getting-started/configuration.md) - Environment and app configuration

### Backend
- [Overview](backend/overview.md) - Backend architecture and design
- [API Reference](backend/api-reference.md) - Complete API documentation
- [Services](backend/services.md) - Backend service implementations
- [Database](backend/database.md) - Database models and schemas
- [Models](backend/models.md) - Data models and validation

### Frontend
- [Overview](frontend/overview.md) - Frontend architecture and design
- [Components](frontend/components.md) - React component documentation
- [Pages](frontend/pages.md) - Next.js page structure
- [State Management](frontend/state.md) - Client-side state management

### Development
- [Contributing](development/contributing.md) - How to contribute to the project
- [Testing](development/testing.md) - Testing guidelines and practices
- [Deployment](development/deployment.md) - Deployment instructions

### API Documentation
- [OpenAPI](api/openapi.md) - OpenAPI specification
- [Endpoints](api/endpoints.md) - Detailed endpoint documentation

## 🔧 Tech Stack

### Backend
- **FastAPI** - Modern Python web framework
- **uv** - Fast Python package manager
- **SQLAlchemy** - Database ORM
- **PostgreSQL** - Primary database
- **OpenAlex API** - Academic paper database
- **MediaCloud API** - News and media database

### Frontend
- **Next.js 14** - React framework with App Router
- **TypeScript** - Type safety
- **Tailwind CSS** - Utility-first CSS framework
- **shadcn/ui** - UI component library
- **NextAuth.js** - Authentication solution

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](development/contributing.md) for details on how to get started.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**Need help?** Check out our [Getting Started](getting-started/quick-start.md) guide or open an issue on GitHub. 