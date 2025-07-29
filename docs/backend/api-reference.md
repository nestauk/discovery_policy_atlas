# API Reference

This section provides comprehensive documentation for the Policy Atlas API endpoints, automatically generated from the FastAPI code.

## Overview

The Policy Atlas API is built with FastAPI and provides RESTful endpoints for:

- **Search**: Query academic papers and policy documents
- **Synthesis**: AI-powered research synthesis
- **Simulation**: Policy outcome modeling
- **Projects**: Project management and data persistence

## Authentication

Most endpoints require authentication. The API uses JWT tokens for authentication.

### Getting an Access Token

```bash
POST /auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password"
}
```

### Using the Token

Include the token in the Authorization header:

```bash
Authorization: Bearer <your-jwt-token>
```

## API Endpoints

### Search Endpoints

The search functionality allows you to query academic papers and policy documents from multiple sources.

#### Search Papers

```python
POST /api/search
```

Search for academic papers and policy documents.

**Request Body:**
```json
{
  "query": "heat pumps policy",
  "max_results": 10,
  "sources": ["openalex", "mediacloud"],
  "filters": {
    "date_from": "2020-01-01",
    "date_to": "2024-01-01"
  }
}
```

**Response:**
```json
{
  "papers": [
    {
      "id": "paper_id",
      "title": "Paper Title",
      "authors": ["Author 1", "Author 2"],
      "abstract": "Paper abstract...",
      "url": "https://doi.org/...",
      "source": "openalex",
      "published_date": "2023-01-01"
    }
  ],
  "total_results": 150,
  "query_time": 1.2
}
```

### Project Management

Manage research projects and organize papers.

#### Create Project

```python
POST /api/projects
```

Create a new research project.

**Request Body:**
```json
{
  "name": "Heat Pump Policy Analysis",
  "description": "Analysis of heat pump adoption policies",
  "tags": ["energy", "policy", "heat-pumps"]
}
```

#### Get Projects

```python
GET /api/projects
```

Retrieve all projects for the authenticated user.

### Synthesis Endpoints

AI-powered synthesis of multiple papers.

#### Create Synthesis

```python
POST /api/synthesis
```

Generate a synthesis report from selected papers.

**Request Body:**
```json
{
  "papers": ["paper_id_1", "paper_id_2"],
  "synthesis_type": "summary",
  "focus_areas": ["policy_impact", "implementation"],
  "project_id": "optional_project_id"
}
```

## Data Models

### Request Models

#### SearchRequest

```python
class SearchRequest(BaseModel):
    query: str
    max_results: int = 10
    sources: List[str] = ["openalex"]
    filters: Optional[SearchFilters] = None
```

#### SynthesisRequest

```python
class SynthesisRequest(BaseModel):
    papers: List[str]
    synthesis_type: str = "summary"
    focus_areas: List[str] = []
    project_id: Optional[str] = None
```

### Response Models

#### SearchResponse

```python
class SearchResponse(BaseModel):
    papers: List[Paper]
    total_results: int
    query_time: float
```

#### Paper

```python
class Paper(BaseModel):
    id: str
    title: str
    authors: List[str]
    abstract: str
    url: str
    source: str
    published_date: str
```

## Error Handling

The API uses standard HTTP status codes and returns error responses in the following format:

```json
{
  "detail": "Error message description",
  "status_code": 400
}
```

### Common Error Codes

- `400 Bad Request` - Invalid request data
- `401 Unauthorized` - Missing or invalid authentication
- `403 Forbidden` - Insufficient permissions
- `404 Not Found` - Resource not found
- `422 Unprocessable Entity` - Validation error
- `500 Internal Server Error` - Server error

## Rate Limiting

API requests are rate-limited to ensure fair usage. Limits are applied per user and endpoint.

## Examples

### Search for Papers

```bash
curl -X POST "http://localhost:8000/api/search" \
  -H "Authorization: Bearer <your-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "heat pumps policy",
    "max_results": 10,
    "sources": ["openalex", "mediacloud"]
  }'
```

### Create a Synthesis

```bash
curl -X POST "http://localhost:8000/api/synthesis" \
  -H "Authorization: Bearer <your-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "papers": ["paper_id_1", "paper_id_2"],
    "synthesis_type": "summary",
    "focus_areas": ["policy_impact", "implementation"]
  }'
```

## Interactive Documentation

For interactive API testing and exploration, visit:

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs) - Interactive API testing interface
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc) - Alternative documentation view

These provide interactive documentation where you can:
- **Test endpoints directly** in your browser
- **See real-time request/response examples**
- **Explore all available parameters and options**
- **Authenticate and make actual API calls**

### Using the Interactive Docs

1. **Navigate to the endpoint** you want to test
2. **Click "Try it out"** to expand the testing interface
3. **Fill in the parameters** (query, request body, etc.)
4. **Click "Execute"** to make a real API call
5. **View the response** with status code, headers, and body

### Authentication

To test authenticated endpoints:
1. Use the `/auth/login` endpoint to get a JWT token
2. Click the "Authorize" button at the top of the page
3. Enter your token in the format: `Bearer your-jwt-token`
4. All subsequent requests will include your authentication 