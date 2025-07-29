# Interactive API Documentation

Policy Atlas provides interactive API documentation that allows you to test endpoints directly in your browser. This is the best way to explore and test the API.

## Available Documentation Interfaces

### Swagger UI
**URL**: [http://localhost:8000/docs](http://localhost:8000/docs) (Development)

**Production URL**: [https://api.policyatlas.org/docs](https://api.policyatlas.org/docs) (When deployed)

The primary interactive documentation interface featuring:
- **Interactive testing** of all endpoints
- **Request/response examples** with real data
- **Authentication support** with JWT tokens
- **Parameter validation** and auto-completion
- **Response schemas** with detailed field descriptions

### ReDoc
**URL**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

An alternative documentation view with:
- **Clean, readable layout** optimized for documentation
- **Search functionality** across all endpoints
- **Responsive design** for mobile devices
- **Better for reading** API specifications

## Getting Started with Interactive Docs

### 1. Start Your Backend Server

```bash
cd backend
uv run python main.py
```

Your API will be available at `http://localhost:8000`

### 2. Access the Documentation

Open your browser and navigate to:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### 3. Test an Endpoint

1. **Find the endpoint** you want to test (e.g., `/api/search`)
2. **Click "Try it out"** to expand the testing interface
3. **Fill in the parameters**:
   - **Request body** (for POST/PUT requests)
   - **Query parameters** (for GET requests)
   - **Path parameters** (if applicable)
4. **Click "Execute"** to make the API call
5. **Review the response** including status code, headers, and body

## Authentication

Most endpoints require authentication. Here's how to authenticate:

### 1. Get a JWT Token

1. **Find the `/auth/login` endpoint** in the documentation
2. **Click "Try it out"**
3. **Enter your credentials**:
   ```json
   {
     "email": "test@example.com",
     "password": "password123"
   }
   ```
4. **Click "Execute"**
5. **Copy the JWT token** from the response

### 2. Authorize Your Requests

1. **Click the "Authorize" button** at the top of the Swagger UI
2. **Enter your token** in the format: `Bearer your-jwt-token`
3. **Click "Authorize"**
4. **Close the dialog**

Now all your API calls will include authentication automatically.

## Example: Testing the Search Endpoint

### Step 1: Navigate to Search Endpoint

1. Open [http://localhost:8000/docs](http://localhost:8000/docs)
2. Find the `POST /api/search` endpoint
3. Click "Try it out"

### Step 2: Fill in the Request

```json
{
  "query": "heat pumps policy",
  "max_results": 5,
  "sources": ["openalex"],
  "filters": {
    "date_from": "2020-01-01",
    "date_to": "2024-01-01"
  }
}
```

### Step 3: Execute and Review

1. Click "Execute"
2. Review the response:
   - **Status Code**: Should be 200 for success
   - **Response Body**: List of papers matching your query
   - **Headers**: Content-Type, etc.

## Common Endpoints to Test

### Search and Discovery
- `POST /api/search` - Search for papers
- `GET /api/papers/{paper_id}` - Get paper details
- `GET /api/sources` - List available data sources

### Project Management
- `GET /api/projects` - List user's projects
- `POST /api/projects` - Create new project
- `PUT /api/projects/{project_id}` - Update project
- `DELETE /api/projects/{project_id}` - Delete project

### Synthesis and Analysis
- `POST /api/synthesis` - Create synthesis report
- `GET /api/synthesis/{synthesis_id}` - Get synthesis details
- `GET /api/synthesis` - List user's syntheses

### Authentication
- `POST /auth/login` - Get JWT token
- `POST /auth/register` - Create new account
- `POST /auth/refresh` - Refresh token

## Tips for Effective Testing

### 1. Start with Simple Requests
- Test unauthenticated endpoints first
- Use simple parameters to verify basic functionality

### 2. Check Response Codes
- **200**: Success
- **201**: Created (for POST requests)
- **400**: Bad Request (check your parameters)
- **401**: Unauthorized (need authentication)
- **404**: Not Found (check the URL)
- **422**: Validation Error (check request format)

### 3. Use Realistic Data
- Test with actual search terms you'd use
- Try different parameter combinations
- Test edge cases (empty queries, large result sets)

### 4. Save Useful Examples
- Copy successful request/response examples
- Document any special parameters or headers
- Note any rate limiting behavior

## Troubleshooting

### Common Issues

**"Failed to fetch" error:**
- Ensure your backend server is running
- Check that the URL is correct
- Verify no CORS issues

**Authentication errors:**
- Make sure you're using the correct token format: `Bearer <token>`
- Check that your token hasn't expired
- Verify the token was copied correctly

**Validation errors:**
- Check the request body format matches the schema
- Ensure all required fields are provided
- Verify data types (strings vs numbers, etc.)

### Getting Help

If you encounter issues:
1. Check the [API Reference](../backend/api-reference.md) for detailed endpoint documentation
2. Review the [Backend Overview](../backend/overview.md) for architecture details
3. Open an issue on GitHub with the specific error details

## Next Steps

- [API Reference](../backend/api-reference.md) - Detailed endpoint documentation
- [Backend Overview](../backend/overview.md) - Architecture and design
- [Installation Guide](../getting-started/installation.md) - Set up your development environment 