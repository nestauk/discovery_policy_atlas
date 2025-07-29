# Backend Overview

The Policy Atlas backend is built with FastAPI and provides a robust API for policy research and analysis.

## Architecture

```
backend/
├── app/
│   ├── api/           # API routes and endpoints
│   ├── core/          # Core configuration and models
│   ├── services/      # Business logic and external integrations
│   ├── utils/         # Utility functions
│   └── main.py        # Application entry point
├── alembic/           # Database migrations
├── tests/             # Test suite
└── requirements.txt   # Python dependencies
```

## Key Components

### API Layer (`app/api/`)

The API layer handles HTTP requests and responses:

- **Routes**: RESTful endpoints for different resources
- **Middleware**: Authentication, CORS, rate limiting
- **Validation**: Request/response validation using Pydantic

### Core (`app/core/`)

Core application configuration and models:

- **Config**: Environment-based configuration
- **Models**: Pydantic models for data validation
- **Database**: Database connection and session management
- **Auth**: Authentication and authorization logic

### Services (`app/services/`)

Business logic and external API integrations:

- **Search Services**: OpenAlex, MediaCloud integrations
- **Synthesis Services**: AI-powered analysis
- **Download Services**: Data export functionality
- **Screening Services**: Paper filtering and ranking

## Technology Stack

### Framework
- **FastAPI**: Modern, fast web framework for building APIs
- **Pydantic**: Data validation using Python type annotations
- **SQLAlchemy**: Database ORM and query builder

### Database
- **PostgreSQL**: Primary database
- **Alembic**: Database migration tool

### External APIs
- **OpenAlex**: Academic paper database
- **MediaCloud**: News and media content
- **Overton**: Policy document database

### Development Tools
- **uv**: Fast Python package manager
- **pytest**: Testing framework
- **pre-commit**: Code quality hooks

## API Design

### RESTful Principles

The API follows RESTful design principles:

- **Resources**: Papers, projects, syntheses
- **HTTP Methods**: GET, POST, PUT, DELETE
- **Status Codes**: Standard HTTP status codes
- **JSON Responses**: Consistent response format

### Authentication

JWT-based authentication system:

```python
# Token-based authentication
Authorization: Bearer <jwt-token>
```

### Rate Limiting

API endpoints are rate-limited to prevent abuse:

- **Search**: 60 requests per minute
- **Synthesis**: 10 requests per minute
- **General**: 1000 requests per hour

## Data Flow

### Search Flow

1. **Request**: Client sends search query
2. **Validation**: Pydantic validates request data
3. **Processing**: Search service queries external APIs
4. **Filtering**: Results are filtered and ranked
5. **Response**: Formatted results returned to client

### Synthesis Flow

1. **Selection**: User selects papers for analysis
2. **Processing**: AI service analyzes selected papers
3. **Generation**: Synthesis report is generated
4. **Storage**: Results saved to database
5. **Response**: Analysis results returned to client

## Error Handling

### Standard Error Responses

```json
{
  "detail": "Error message",
  "status_code": 400,
  "error_type": "validation_error"
}
```

### Error Types

- **ValidationError**: Invalid request data
- **AuthenticationError**: Missing or invalid credentials
- **AuthorizationError**: Insufficient permissions
- **NotFoundError**: Resource not found
- **RateLimitError**: Too many requests

## Performance

### Optimization Strategies

- **Connection Pooling**: Database connection reuse
- **Caching**: Redis-based response caching
- **Async Processing**: Non-blocking I/O operations
- **Pagination**: Large result set handling

### Monitoring

- **Logging**: Structured logging with different levels
- **Metrics**: Request timing and error rates
- **Health Checks**: Application health monitoring

## Security

### Authentication

- JWT tokens with configurable expiration
- Secure password hashing
- Session management

### Authorization

- Role-based access control
- Resource-level permissions
- API key management

### Data Protection

- Input validation and sanitization
- SQL injection prevention
- CORS configuration

## Development Workflow

### Local Development

```bash
# Start development server
uv run python main.py

# Run tests
uv run pytest

# Check code quality
uv run pre-commit run
```

### Database Management

```bash
# Create migration
uv run alembic revision --autogenerate -m "description"

# Apply migrations
uv run alembic upgrade head

# Rollback migration
uv run alembic downgrade -1
```

## Deployment

### Environment Configuration

- **Development**: Local PostgreSQL, debug logging
- **Staging**: Staging database, info logging
- **Production**: Production database, warning logging

### Containerization

Docker support for easy deployment:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Next Steps

- [API Reference](api-reference.md) - Detailed API documentation
- [Services](services.md) - Service layer documentation
- [Database](database.md) - Database schema and models
- [Models](models.md) - Data models and validation 