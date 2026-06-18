"""
MCP (Model Context Protocol) server for Policy Atlas.

Exposes Policy Atlas capabilities as MCP tools so autonomous agents
(Claude Desktop, Microsoft Copilot Cowork, etc.) can call them.

Tools are thin facades over services in `app/services/`. All business
logic lives in the service layer — see docs/mcp_integration_plan.md.
"""
