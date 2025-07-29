# OpenAPI Specification

Policy Atlas uses the OpenAPI specification to provide comprehensive API documentation. This page explains how to access and use the OpenAPI specification.

## What is OpenAPI?

OpenAPI (formerly Swagger) is a specification for documenting REST APIs. It provides:

- **Machine-readable** API documentation
- **Interactive testing** capabilities
- **Code generation** for client libraries
- **Standard format** for API documentation

## Accessing the OpenAPI Specification

### JSON Format
**URL**: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

This provides the raw OpenAPI specification in JSON format, useful for:
- Code generation tools
- API client libraries
- Integration with other tools

### YAML Format
**URL**: [http://localhost:8000/openapi.yaml](http://localhost:8000/openapi.yaml)

The same specification in YAML format, which is more human-readable.

## Using the OpenAPI Specification

### 1. Code Generation

You can use the OpenAPI specification to generate client libraries:

```bash
# Generate Python client
npx @openapitools/openapi-generator-cli generate \
  -i http://localhost:8000/openapi.json \
  -g python \
  -o ./generated/python-client

# Generate TypeScript client
npx @openapitools/openapi-generator-cli generate \
  -i http://localhost:8000/openapi.json \
  -g typescript-fetch \
  -o ./generated/typescript-client
```

### 2. API Testing Tools

Import the specification into tools like:
- **Postman**: Import the OpenAPI JSON
- **Insomnia**: Use the OpenAPI URL
- **curl**: Use the specification to understand endpoints

### 3. Documentation Tools

Use the specification with documentation tools:
- **Stoplight Studio**: Import for enhanced documentation
- **Redoc**: Generate custom documentation sites
- **Swagger UI**: Custom deployments

## Specification Structure

The OpenAPI specification includes:

### Info Section
```yaml
info:
  title: Policy Atlas API
  description: AI-powered policy research and analysis platform
  version: 1.0.0
  contact:
    name: Policy Atlas Team
    email: team@policyatlas.org
```

### Servers
```yaml
servers:
  - url: http://localhost:8000
    description: Development server
  - url: https://api.policyatlas.org
    description: Production server
```

### Paths
Each API endpoint is documented with:
- **HTTP method** (GET, POST, PUT, DELETE)
- **Path parameters**
- **Query parameters**
- **Request body schema**
- **Response schemas**
- **Authentication requirements**

### Components
Reusable schemas for:
- **Request models** (SearchRequest, SynthesisRequest)
- **Response models** (SearchResponse, Paper)
- **Security schemes** (JWT authentication)

## Example: Search Endpoint Specification

```yaml
/api/search:
  post:
    summary: Search for academic papers and policy documents
    description: |
      Search across multiple sources including OpenAlex and MediaCloud
      to find relevant academic papers and policy documents.
    security:
      - bearerAuth: []
    requestBody:
      required: true
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/SearchRequest'
          example:
            query: "heat pumps policy"
            max_results: 10
            sources: ["openalex", "mediacloud"]
    responses:
      '200':
        description: Successful search results
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/SearchResponse'
      '401':
        description: Unauthorized
      '422':
        description: Validation error
```

## Security

The API uses JWT Bearer token authentication:

```yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
```

## Validation

The OpenAPI specification includes validation rules:

- **Required fields** are marked as required
- **Data types** are specified (string, integer, boolean)
- **Format validation** (email, date, etc.)
- **Enum values** for constrained fields
- **Minimum/maximum** values for numeric fields

## Extending the Specification

### Adding Custom Documentation

You can enhance the OpenAPI specification in your FastAPI code:

```python
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

app = FastAPI(
    title="Policy Atlas API",
    description="AI-powered policy research and analysis platform",
    version="1.0.0",
    contact={
        "name": "Policy Atlas Team",
        "email": "team@policyatlas.org",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
)

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="Policy Atlas API",
        version="1.0.0",
        description="AI-powered policy research and analysis platform",
        routes=app.routes,
    )
    
    # Add custom properties
    openapi_schema["info"]["x-logo"] = {
        "url": "https://policyatlas.org/logo.png"
    }
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi
```

### Adding Examples

Include realistic examples in your Pydantic models:

```python
from pydantic import BaseModel, Field

class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query", example="heat pumps policy")
    max_results: int = Field(10, ge=1, le=100, description="Maximum number of results")
    sources: List[str] = Field(["openalex"], description="Data sources to search")
    
    class Config:
        schema_extra = {
            "example": {
                "query": "heat pumps policy",
                "max_results": 10,
                "sources": ["openalex", "mediacloud"]
            }
        }
```

## Tools and Integrations

### Development Tools
- **FastAPI**: Automatically generates OpenAPI spec
- **Pydantic**: Provides schema validation
- **uvicorn**: Serves the specification

### Documentation Tools
- **Swagger UI**: Interactive documentation
- **ReDoc**: Alternative documentation view
- **Stoplight**: Professional API documentation

### Testing Tools
- **Postman**: Import OpenAPI spec
- **Insomnia**: API testing and design
- **curl**: Command-line testing

## Next Steps

- [Interactive API Docs](interactive-docs.md) - Test endpoints directly
- [API Reference](../backend/api-reference.md) - Detailed endpoint documentation
- [Backend Overview](../backend/overview.md) - Architecture and design 