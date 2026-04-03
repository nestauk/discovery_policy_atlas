"""
Pydantic models for chatbot service.
"""

from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from datetime import datetime
from enum import Enum


class ChatRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(BaseModel):
    """A single chat message."""

    role: ChatRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ChatRequest(BaseModel):
    """Request to send a message to the chatbot."""

    message: str = Field(..., min_length=1, max_length=2000)
    recent_messages: Optional[List[ChatMessage]] = Field(default=None, max_items=10)


class DocumentReference(BaseModel):
    """Reference to a source document used in the response."""

    document_id: str
    title: str
    authors: Optional[List[str]] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    chunk_type: Optional[str] = None
    relevance_score: Optional[float] = None
    published_date: Optional[str] = None
    year: Optional[int] = None


class ChatStep(BaseModel):
    """A single visible chatbot activity step."""

    id: str
    type: Literal["status", "tool", "message"]
    label: str
    status: Literal["pending", "running", "completed", "failed"]
    summary: Optional[str] = None


class ChatEvent(BaseModel):
    """A streamed chatbot activity event."""

    type: Literal[
        "agent.status",
        "tool.started",
        "tool.completed",
        "tool.failed",
        "message.completed",
        "message.failed",
    ]
    step: Optional[ChatStep] = None
    message: Optional[str] = None
    references: List[DocumentReference] = Field(default_factory=list)
    activity_summary: Optional[str] = None
    error: Optional[str] = None


class ChatResponse(BaseModel):
    """Response from the chatbot."""

    message: str
    references: List[DocumentReference] = Field(default_factory=list)
    steps: List[ChatStep] = Field(default_factory=list)
    activity_summary: Optional[str] = None
    context_used: Optional[str] = None  # For debugging
