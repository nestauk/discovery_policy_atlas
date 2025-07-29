# Contributing to Policy Atlas

Thank you for your interest in contributing to Policy Atlas! This guide will help you get started.

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+
- Git
- uv (Python package manager)

### Development Setup

1. **Fork and Clone**
   ```bash
   git clone https://github.com/yourusername/discovery_policy_atlas.git
   cd discovery_policy_atlas
   ```

2. **Setup Backend**
   ```bash
   cd backend
   uv sync
   uv run pre-commit install
   ```

3. **Setup Frontend**
   ```bash
   cd ../frontend
   npm install --legacy-peer-deps
   ```

## Development Workflow

### 1. Create a Feature Branch

```bash
git checkout -b feature/your-feature-name
```

### 2. Make Your Changes

- Follow the existing code style
- Write tests for new functionality
- Update documentation as needed

### 3. Test Your Changes

**Backend Tests:**
```bash
cd backend
uv run pytest
```

**Frontend Tests:**
```bash
cd frontend
npm run test
```

**Code Quality:**
```bash
cd backend
uv run pre-commit run
```

### 4. Commit Your Changes

```bash
git add .
git commit -m "feat: add new search functionality"
```

### 5. Push and Create Pull Request

```bash
git push origin feature/your-feature-name
```

## Code Style

### Python (Backend)

- Use **Black** for code formatting
- Use **Ruff** for linting
- Follow **PEP 8** guidelines
- Use type hints for all functions

### TypeScript/JavaScript (Frontend)

- Use **Prettier** for formatting
- Use **ESLint** for linting
- Follow **React** best practices
- Use **TypeScript** for type safety

## Testing

### Backend Testing

```bash
cd backend

# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_api.py

# Run with coverage
uv run pytest --cov=app
```

### Frontend Testing

```bash
cd frontend

# Run tests
npm run test

# Run tests in watch mode
npm run test:watch

# Run tests with coverage
npm run test:coverage
```

## Documentation

### Updating Documentation

1. **API Documentation**: Update docstrings in FastAPI endpoints
2. **Component Documentation**: Add JSDoc comments to React components
3. **README**: Update main README for significant changes
4. **MkDocs**: Update documentation in `docs/` directory

### Building Documentation

```bash
cd backend
uv run mkdocs build --config-file ../mkdocs.yml
uv run mkdocs serve --config-file ../mkdocs.yml
```

## Pull Request Guidelines

### Before Submitting

- [ ] Code follows style guidelines
- [ ] Tests pass locally
- [ ] Documentation is updated
- [ ] No breaking changes (or documented)

### PR Description

Include:
- **Summary**: Brief description of changes
- **Motivation**: Why this change is needed
- **Testing**: How to test the changes
- **Screenshots**: For UI changes

## Issue Reporting

### Bug Reports

Include:
- **Description**: Clear description of the bug
- **Steps to Reproduce**: Detailed steps
- **Expected vs Actual**: What should happen vs what happens
- **Environment**: OS, browser, versions

### Feature Requests

Include:
- **Description**: What you want to achieve
- **Use Case**: Why this feature is needed
- **Mockups**: If applicable

## Community Guidelines

### Code of Conduct

- Be respectful and inclusive
- Help others learn and grow
- Provide constructive feedback
- Follow the project's coding standards

### Communication

- **GitHub Issues**: For bugs and feature requests
- **Discussions**: For questions and ideas
- **Pull Requests**: For code contributions

## Getting Help

### Resources

- [Installation Guide](../getting-started/installation.md)
- [API Reference](../backend/api-reference.md)
- [Frontend Guide](../frontend/overview.md)

### Questions?

- Open a [GitHub Issue](https://github.com/yourusername/discovery_policy_atlas/issues)
- Join our [Discord/Slack](link-to-community)
- Check existing [Discussions](https://github.com/yourusername/discovery_policy_atlas/discussions)

## Recognition

Contributors will be recognized in:
- Project README
- Release notes
- Contributor hall of fame

Thank you for contributing to Policy Atlas! 🎉 