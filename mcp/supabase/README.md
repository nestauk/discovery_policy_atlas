# Supabase MCP Server

Read-only MCP server for querying the Policy Atlas Supabase database.

## Tools

### Basic Operations

| Tool | Description |
|------|-------------|
| `list_tables` | List all tables in the database |
| `describe_table` | Get column types and sample values for a table |
| `count_rows` | Count rows, optionally grouped by column |

### Query Operations

| Tool | Description |
|------|-------------|
| `sample_rows` | Get rows with filtering, ordering, and column selection |
| `run_query` | Execute arbitrary SELECT queries (requires DB function) |
| `get_row_by_id` | Fetch a single row by primary key |

### Relationship Operations

| Tool | Description |
|------|-------------|
| `get_related` | Get related rows via foreign key relationships |
| `explain_schema` | Show foreign key relationships between tables |

## Usage Examples

### sample_rows with filters

```json
{
  "table_name": "synthesis_runs",
  "where": "status=completed",
  "order_by": "-created_at",
  "limit": 10
}
```

### get_related

```json
{
  "from_table": "synthesis_runs",
  "id": "abc-123",
  "to_table": "synthesis_citations"
}
```

### explain_schema

```json
{
  "table_name": "synthesis_citations"
}
```

Output:
```
Schema for 'synthesis_citations':

  Primary Key: id

  Belongs To:
    → synthesis_runs (via synthesis_run_id)
    → analysis_documents (via analysis_document_id)
```

## Filter Syntax

The `where` parameter supports:

- Equality: `status=completed`
- Inequality: `status!=pending`
- Comparison: `count>10`, `created_at<2024-01-01`
- LIKE/ILIKE: `title ILIKE %obesity%`
- Multiple conditions: `status=completed AND version>1`

## Setup

1. Ensure `backend/.env` contains `SUPABASE_URL` and `SUPABASE_KEY`
2. Run `npm install` in this directory
3. Add to Cursor MCP config:

```json
{
  "mcpServers": {
    "supabase": {
      "command": "node",
      "args": ["/path/to/mcp/supabase/index.js"]
    }
  }
}
```

## Note on run_query

The `run_query` tool requires a database function for arbitrary SQL. Without it, use `sample_rows` with filters for most queries.



