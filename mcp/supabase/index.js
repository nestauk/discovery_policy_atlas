#!/usr/bin/env node

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { createClient } from "@supabase/supabase-js";
import { config } from "dotenv";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

// Load .env from backend folder (two levels up from mcp/supabase/)
const __dirname = dirname(fileURLToPath(import.meta.url));
config({ path: resolve(__dirname, "../../backend/.env") });

const supabaseUrl = process.env.SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_KEY;

if (!supabaseUrl || !supabaseKey) {
  console.error("Missing SUPABASE_URL or SUPABASE_KEY in backend/.env");
  process.exit(1);
}

const supabase = createClient(supabaseUrl, supabaseKey);

// Schema relationships for explain_schema and get_related
const SCHEMA_RELATIONSHIPS = {
  analysis_projects: {
    primary_key: "id",
    has_many: [
      { table: "analysis_documents", foreign_key: "analysis_project_id" },
      { table: "synthesis_runs", foreign_key: "analysis_project_id" }
    ]
  },
  analysis_documents: {
    primary_key: "id",
    belongs_to: [
      { table: "analysis_projects", foreign_key: "analysis_project_id" }
    ],
    has_many: [
      { table: "analysis_extractions", foreign_key: "analysis_document_id" },
      { table: "document_chunks", foreign_key: "analysis_document_id" },
      { table: "synthesis_citations", foreign_key: "analysis_document_id" }
    ]
  },
  analysis_extractions: {
    primary_key: "id",
    belongs_to: [
      { table: "analysis_documents", foreign_key: "analysis_document_id" }
    ]
  },
  synthesis_runs: {
    primary_key: "id",
    belongs_to: [
      { table: "analysis_projects", foreign_key: "analysis_project_id" }
    ],
    has_many: [
      { table: "synthesis_citations", foreign_key: "synthesis_run_id" },
      { table: "synthesis_themes", foreign_key: "synthesis_run_id" },
      { table: "synthesis_outcome_themes", foreign_key: "synthesis_run_id" }
    ]
  },
  synthesis_citations: {
    primary_key: "id",
    belongs_to: [
      { table: "synthesis_runs", foreign_key: "synthesis_run_id" },
      { table: "analysis_documents", foreign_key: "analysis_document_id" }
    ]
  },
  synthesis_themes: {
    primary_key: "id",
    belongs_to: [
      { table: "synthesis_runs", foreign_key: "synthesis_run_id" }
    ]
  },
  synthesis_outcome_themes: {
    primary_key: "id",
    belongs_to: [
      { table: "synthesis_runs", foreign_key: "synthesis_run_id" }
    ],
    has_many: [
      { table: "outcome_theme_assignments", foreign_key: "outcome_theme_id" }
    ]
  },
  outcome_theme_assignments: {
    primary_key: "id",
    belongs_to: [
      { table: "synthesis_outcome_themes", foreign_key: "outcome_theme_id" }
    ]
  },
  chunks: {
    primary_key: "id",
    belongs_to: [
      { table: "analysis_documents", foreign_key: "document_id" }
    ]
  },
  theme_assignments: {
    primary_key: "id",
    belongs_to: [
      { table: "synthesis_themes", foreign_key: "synthesis_theme_id" },
      { table: "analysis_extractions", foreign_key: "extraction_id" }
    ]
  },
  user_feedback: {
    primary_key: "id",
    belongs_to: [
      { table: "analysis_projects", foreign_key: "project_id" }
    ]
  }
};

const server = new Server(
  { name: "mcp-supabase", version: "2.0.0" },
  { capabilities: { tools: {} } }
);

// List available tools
server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "list_tables",
      description: "List all tables in the Supabase database",
      inputSchema: { type: "object", properties: {} }
    },
    {
      name: "describe_table",
      description: "Get column information for a specific table",
      inputSchema: {
        type: "object",
        properties: {
          table_name: { type: "string", description: "Name of the table to describe" }
        },
        required: ["table_name"]
      }
    },
    {
      name: "sample_rows",
      description: "Get sample rows from a table with optional filtering",
      inputSchema: {
        type: "object",
        properties: {
          table_name: { type: "string", description: "Name of the table" },
          limit: { type: "number", description: "Number of rows to return (default 5, max 100)" },
          columns: { type: "string", description: "Comma-separated list of columns to select (default: all)" },
          where: { type: "string", description: "Filter condition, e.g. 'status=completed' or 'id=abc-123'" },
          order_by: { type: "string", description: "Column to order by (prefix with - for descending, e.g. '-created_at')" }
        },
        required: ["table_name"]
      }
    },
    {
      name: "count_rows",
      description: "Count rows in a table, optionally grouped by a column",
      inputSchema: {
        type: "object",
        properties: {
          table_name: { type: "string", description: "Name of the table" },
          column: { type: "string", description: "Column to group by (optional)" },
          where: { type: "string", description: "Filter condition (optional)" }
        },
        required: ["table_name"]
      }
    },
    {
      name: "run_query",
      description: "Execute a read-only SQL SELECT query. Only SELECT statements are allowed.",
      inputSchema: {
        type: "object",
        properties: {
          query: { 
            type: "string", 
            description: "SQL SELECT query to execute. Must start with SELECT. Example: SELECT c.*, d.title FROM synthesis_citations c JOIN analysis_documents d ON c.analysis_document_id = d.id WHERE c.synthesis_run_id = 'xxx' LIMIT 10" 
          }
        },
        required: ["query"]
      }
    },
    {
      name: "get_row_by_id",
      description: "Fetch a single row by its primary key",
      inputSchema: {
        type: "object",
        properties: {
          table_name: { type: "string", description: "Name of the table" },
          id: { type: "string", description: "Primary key value (usually UUID)" },
          columns: { type: "string", description: "Comma-separated columns to return (default: all)" }
        },
        required: ["table_name", "id"]
      }
    },
    {
      name: "get_related",
      description: "Get related rows from another table via foreign key relationship",
      inputSchema: {
        type: "object",
        properties: {
          from_table: { type: "string", description: "Source table name" },
          id: { type: "string", description: "ID of the source row" },
          to_table: { type: "string", description: "Related table to fetch from" },
          limit: { type: "number", description: "Max rows to return (default 20)" }
        },
        required: ["from_table", "id", "to_table"]
      }
    },
    {
      name: "explain_schema",
      description: "Show foreign key relationships between tables",
      inputSchema: {
        type: "object",
        properties: {
          table_name: { type: "string", description: "Specific table to explain (optional, shows all if omitted)" }
        }
      }
    }
  ]
}));

// Parse simple where conditions like "status=completed" or "id=abc-123"
function parseWhere(whereStr) {
  if (!whereStr) return null;
  
  const conditions = [];
  const parts = whereStr.split(/\s+AND\s+/i);
  
  for (const part of parts) {
    const match = part.match(/^(\w+)\s*(=|!=|>|<|>=|<=|LIKE|ILIKE)\s*(.+)$/i);
    if (match) {
      let [, column, operator, value] = match;
      value = value.trim().replace(/^['"]|['"]$/g, ''); // Remove quotes
      conditions.push({ column, operator: operator.toLowerCase(), value });
    }
  }
  
  return conditions.length > 0 ? conditions : null;
}

// Apply where conditions to a Supabase query
function applyWhere(query, conditions) {
  if (!conditions) return query;
  
  for (const { column, operator, value } of conditions) {
    switch (operator) {
      case '=':
        query = query.eq(column, value);
        break;
      case '!=':
        query = query.neq(column, value);
        break;
      case '>':
        query = query.gt(column, value);
        break;
      case '<':
        query = query.lt(column, value);
        break;
      case '>=':
        query = query.gte(column, value);
        break;
      case '<=':
        query = query.lte(column, value);
        break;
      case 'like':
        query = query.like(column, value);
        break;
      case 'ilike':
        query = query.ilike(column, value);
        break;
    }
  }
  return query;
}

// Handle tool calls
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    switch (name) {
      case "list_tables": {
        const tables = Object.keys(SCHEMA_RELATIONSHIPS);
        const msg = [
          "Available tables (from schema relationships map):",
          ...tables
        ].join("\n");
        return { content: [{ type: "text", text: msg }] };
      }

      case "describe_table": {
        const tableName = args.table_name;
        
        const { data, error } = await supabase
          .from(tableName)
          .select("*")
          .limit(1);
        
        if (error) {
          return { content: [{ type: "text", text: `Error: ${error.message}` }] };
        }
        
        if (!data || data.length === 0) {
          return { content: [{ type: "text", text: `Table '${tableName}' is empty or doesn't exist` }] };
        }
        
        const columns = Object.keys(data[0]);
        const sample = data[0];
        
        const description = columns.map(col => {
          const val = sample[col];
          const type = val === null ? "null" : Array.isArray(val) ? "array" : typeof val;
          const preview = val === null ? "null" : 
            typeof val === "object" ? JSON.stringify(val).slice(0, 60) :
            String(val).slice(0, 60);
          return `  ${col}: ${type} = ${preview}`;
        }).join("\n");
        
        return { content: [{ type: "text", text: `Columns in '${tableName}':\n\n${description}` }] };
      }

      case "sample_rows": {
        const tableName = args.table_name;
        const limit = Math.min(args.limit || 5, 100);
        const columns = args.columns || "*";
        const orderBy = args.order_by;
        
        let query = supabase.from(tableName).select(columns);
        
        // Apply where conditions
        const conditions = parseWhere(args.where);
        query = applyWhere(query, conditions);
        
        // Apply ordering
        if (orderBy) {
          const desc = orderBy.startsWith('-');
          const col = desc ? orderBy.slice(1) : orderBy;
          query = query.order(col, { ascending: !desc });
        }
        
        query = query.limit(limit);
        
        const { data, error } = await query;
        
        if (error) {
          return { content: [{ type: "text", text: `Error: ${error.message}` }] };
        }
        
        return {
          content: [{ type: "text", text: JSON.stringify(data, null, 2) }]
        };
      }

      case "count_rows": {
        const tableName = args.table_name;
        const column = args.column;
        const conditions = parseWhere(args.where);
        
        if (column) {
          let query = supabase.from(tableName).select(`${column}, count`);
          query = applyWhere(query, conditions);
          query = query.order('count', { ascending: false });
          
          const { data, error } = await query;
          
          if (error) {
            return { content: [{ type: "text", text: `Error: ${error.message}` }] };
          }
          
          const sorted = (data || [])
            .map((row) => `  ${row[column] ?? "(null)"}: ${row.count}`)
            .join("\n");
          
          return { content: [{ type: "text", text: `Counts by '${column}' in '${tableName}':\n\n${sorted}` }] };
        } else {
          let query = supabase.from(tableName).select("*", { count: "exact", head: true });
          query = applyWhere(query, conditions);
          
          const { count, error } = await query;
          
          if (error) {
            return { content: [{ type: "text", text: `Error: ${error.message}` }] };
          }
          
          return { content: [{ type: "text", text: `Total rows in '${tableName}': ${count}` }] };
        }
      }

      case "run_query": {
        const query = args.query?.trim();
        
        // Security: only allow SELECT queries
        if (!query || !query.toUpperCase().startsWith('SELECT')) {
          return { 
            content: [{ type: "text", text: "Error: Only SELECT queries are allowed. Query must start with SELECT." }] 
          };
        }
        
        // Block dangerous keywords
        const dangerous = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'TRUNCATE', 'ALTER', 'CREATE', 'GRANT', 'REVOKE'];
        const upperQuery = query.toUpperCase();
        for (const keyword of dangerous) {
          if (upperQuery.includes(keyword)) {
            return { 
              content: [{ type: "text", text: `Error: Query contains forbidden keyword: ${keyword}` }] 
            };
          }
        }
        
        const { data, error } = await supabase.rpc('run_readonly_query', { query_text: query });
        
        if (error) {
          // If RPC doesn't exist, try raw query via postgrest (limited)
          return { 
            content: [{ 
              type: "text", 
              text: `Error: ${error.message}\n\nNote: run_query requires a database function. Use sample_rows with filters for basic queries, or create the function:\n\nCREATE OR REPLACE FUNCTION run_readonly_query(query_text TEXT)\nRETURNS JSON AS $$\nBEGIN\n  RETURN (SELECT json_agg(row_to_json(t)) FROM (SELECT * FROM (SELECT query_text) AS subq) t);\nEND;\n$$ LANGUAGE plpgsql SECURITY DEFINER;`
            }] 
          };
        }
        
        return {
          content: [{ type: "text", text: JSON.stringify(data, null, 2) }]
        };
      }

      case "get_row_by_id": {
        const tableName = args.table_name;
        const id = args.id;
        const columns = args.columns || "*";
        
        const pk = SCHEMA_RELATIONSHIPS[tableName]?.primary_key || "id";
        
        const { data, error } = await supabase
          .from(tableName)
          .select(columns)
          .eq(pk, id)
          .single();
        
        if (error) {
          return { content: [{ type: "text", text: `Error: ${error.message}` }] };
        }
        
        return {
          content: [{ type: "text", text: JSON.stringify(data, null, 2) }]
        };
      }

      case "get_related": {
        const fromTable = args.from_table;
        const id = args.id;
        const toTable = args.to_table;
        const limit = Math.min(args.limit || 20, 100);
        
        const schema = SCHEMA_RELATIONSHIPS[fromTable];
        if (!schema) {
          return { content: [{ type: "text", text: `Unknown table: ${fromTable}` }] };
        }
        
        // Find the relationship
        let foreignKey = null;
        let direction = null;
        
        // Check has_many relationships
        const hasMany = schema.has_many?.find(r => r.table === toTable);
        if (hasMany) {
          foreignKey = hasMany.foreign_key;
          direction = 'has_many';
        }
        
        // Check belongs_to relationships (reverse lookup)
        const belongsTo = schema.belongs_to?.find(r => r.table === toTable);
        if (belongsTo) {
          // For belongs_to, we need to get the FK value from source row first
          const pk = schema.primary_key || "id";
          const { data: sourceRow, error: sourceError } = await supabase
            .from(fromTable)
            .select(belongsTo.foreign_key)
            .eq(pk, id)
            .single();
          
          if (sourceError || !sourceRow) {
            return { content: [{ type: "text", text: `Error finding source row: ${sourceError?.message}` }] };
          }
          
          const relatedId = sourceRow[belongsTo.foreign_key];
          const targetPk = SCHEMA_RELATIONSHIPS[toTable]?.primary_key || "id";
          
          const { data, error } = await supabase
            .from(toTable)
            .select("*")
            .eq(targetPk, relatedId)
            .limit(1);
          
          if (error) {
            return { content: [{ type: "text", text: `Error: ${error.message}` }] };
          }
          
          return {
            content: [{ type: "text", text: JSON.stringify(data, null, 2) }]
          };
        }
        
        if (!foreignKey) {
          return { 
            content: [{ 
              type: "text", 
              text: `No relationship found from '${fromTable}' to '${toTable}'. Use explain_schema to see available relationships.` 
            }] 
          };
        }
        
        // For has_many, query the related table
        const { data, error } = await supabase
          .from(toTable)
          .select("*")
          .eq(foreignKey, id)
          .limit(limit);
        
        if (error) {
          return { content: [{ type: "text", text: `Error: ${error.message}` }] };
        }
        
        return {
          content: [{ 
            type: "text", 
            text: `Found ${data.length} related rows in '${toTable}' (via ${foreignKey}):\n\n${JSON.stringify(data, null, 2)}` 
          }]
        };
      }

      case "explain_schema": {
        const tableName = args.table_name;
        
        if (tableName) {
          const schema = SCHEMA_RELATIONSHIPS[tableName];
          if (!schema) {
            return { content: [{ type: "text", text: `Unknown table: ${tableName}` }] };
          }
          
          let output = `Schema for '${tableName}':\n\n`;
          output += `  Primary Key: ${schema.primary_key || 'id'}\n`;
          
          if (schema.belongs_to?.length) {
            output += `\n  Belongs To:\n`;
            for (const rel of schema.belongs_to) {
              output += `    → ${rel.table} (via ${rel.foreign_key})\n`;
            }
          }
          
          if (schema.has_many?.length) {
            output += `\n  Has Many:\n`;
            for (const rel of schema.has_many) {
              output += `    ← ${rel.table} (via ${rel.foreign_key})\n`;
            }
          }
          
          return { content: [{ type: "text", text: output }] };
        }
        
        // Show all relationships
        let output = "Database Schema Relationships:\n\n";
        
        for (const [table, schema] of Object.entries(SCHEMA_RELATIONSHIPS)) {
          output += `${table}:\n`;
          
          if (schema.belongs_to?.length) {
            for (const rel of schema.belongs_to) {
              output += `  → ${rel.table} (${rel.foreign_key})\n`;
            }
          }
          if (schema.has_many?.length) {
            for (const rel of schema.has_many) {
              output += `  ← ${rel.table} (${rel.foreign_key})\n`;
            }
          }
          output += "\n";
        }
        
        return { content: [{ type: "text", text: output }] };
      }

      default:
        return { content: [{ type: "text", text: `Unknown tool: ${name}` }] };
    }
  } catch (err) {
    return { content: [{ type: "text", text: `Error: ${err.message}` }] };
  }
});

// Start server
const transport = new StdioServerTransport();
await server.connect(transport);
