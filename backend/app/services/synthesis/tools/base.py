"""
Base classes and utilities for agentic briefing tools.

Provides the foundation for tool definitions, registration, and execution
with integrated Langfuse tracing.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)


def _trace_tool_execution(
    tool_name: str,
    state: Dict[str, Any],
    kwargs: Dict[str, Any],
    result: "ToolResult",
    duration_ms: float,
) -> None:
    """Log tool execution to Langfuse if handler is available.

    Args:
        tool_name: Name of the executed tool.
        state: Synthesis state (contains langfuse_handler).
        kwargs: Tool input parameters.
        result: Tool execution result.
        duration_ms: Execution duration in milliseconds.
    """
    handler = state.get("langfuse_handler")
    if not handler:
        return

    try:
        # The handler is a LangchainCallbackHandler - log via metadata
        # Tool execution is logged through standard logging; Langfuse captures via LLM callbacks
        # For now, skip manual span creation as LangchainCallbackHandler doesn't expose trace API
        pass
    except Exception as e:
        logger.warning(f"Failed to trace tool execution: {e}")


@dataclass
class ToolResult:
    """Result from a tool execution.

    Attributes:
        success: Whether the tool executed successfully.
        data: The returned data (if successful).
        error: Error message (if failed).
        fallback_used: Whether fallback to pre-computed RCS was used.
    """

    success: bool
    data: Any = None
    error: Optional[str] = None
    fallback_used: bool = False

    @classmethod
    def ok(cls, data: Any, fallback_used: bool = False) -> "ToolResult":
        """Create a successful result."""
        return cls(success=True, data=data, fallback_used=fallback_used)

    @classmethod
    def fail(cls, error: str) -> "ToolResult":
        """Create a failed result."""
        return cls(success=False, error=error)


class ToolInput(BaseModel):
    """Base class for tool input parameters."""

    pass


class BaseTool(ABC):
    """Abstract base class for agentic briefing tools.

    Tools are stateless functions that query evidence from pre-computed
    state or the database. Each tool should:
    - Have a clear, single purpose
    - Return structured data with citations
    - Fall back to pre-computed RCS if queries return empty
    - Include Langfuse tracing for observability

    Attributes:
        name: Unique tool identifier.
        description: Human-readable description for the orchestrator.
        max_results: Default maximum results to return.
    """

    name: str
    description: str
    max_results: int = 5

    @abstractmethod
    async def execute(
        self,
        state: Dict[str, Any],
        **kwargs,
    ) -> ToolResult:
        """Execute the tool with the given parameters.

        Args:
            state: The current SynthesisState dictionary.
            **kwargs: Tool-specific parameters.

        Returns:
            ToolResult with data or error.
        """
        pass

    def get_schema(self) -> Dict[str, Any]:
        """Get the tool schema for LLM function calling.

        Returns:
            OpenAI-compatible function schema.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self._get_parameters_schema(),
            },
        }

    @abstractmethod
    def _get_parameters_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for tool parameters.

        Returns:
            JSON schema for the tool's input parameters.
        """
        pass


T = TypeVar("T", bound=BaseTool)


class ToolRegistry:
    """Registry for available tools.

    Manages tool registration and lookup for the orchestrator.
    Provides schemas for LLM function calling.
    """

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance.

        Args:
            tool: Tool instance to register.
        """
        if tool.name in self._tools:
            logger.warning(f"Overwriting existing tool: {tool.name}")
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def get(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name.

        Args:
            name: Tool name.

        Returns:
            Tool instance or None if not found.
        """
        return self._tools.get(name)

    def get_all(self) -> List[BaseTool]:
        """Get all registered tools.

        Returns:
            List of all tool instances.
        """
        return list(self._tools.values())

    def get_schemas(self) -> List[Dict[str, Any]]:
        """Get schemas for all registered tools.

        Returns:
            List of OpenAI-compatible function schemas.
        """
        return [tool.get_schema() for tool in self._tools.values()]

    async def execute(
        self,
        tool_name: str,
        state: Dict[str, Any],
        **kwargs,
    ) -> ToolResult:
        """Execute a tool by name with Langfuse tracing.

        Args:
            tool_name: Name of the tool to execute.
            state: Current synthesis state.
            **kwargs: Tool-specific parameters.

        Returns:
            ToolResult from the tool execution.
        """
        tool = self.get(tool_name)
        if not tool:
            return ToolResult.fail(f"Unknown tool: {tool_name}")

        start_time = time.time()
        try:
            result = await tool.execute(state, **kwargs)
            duration_ms = (time.time() - start_time) * 1000

            # Trace to Langfuse
            _trace_tool_execution(tool_name, state, kwargs, result, duration_ms)

            return result
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            result = ToolResult.fail(str(e))

            # Trace error to Langfuse
            _trace_tool_execution(tool_name, state, kwargs, result, duration_ms)

            logger.error(f"Tool {tool_name} failed: {e}")
            return result


# Global registry instance
_registry = ToolRegistry()


def get_tool_registry() -> ToolRegistry:
    """Get the global tool registry.

    Returns:
        The singleton ToolRegistry instance.
    """
    return _registry


def register_tool(tool: BaseTool) -> BaseTool:
    """Register a tool with the global registry.

    Args:
        tool: Tool instance to register.

    Returns:
        The registered tool (for chaining).
    """
    _registry.register(tool)
    return tool
