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


class ChatMode(str, Enum):
    DEFAULT = "default"
    FORECAST = "forecast"


class ChatMessage(BaseModel):
    """A single chat message."""

    role: ChatRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ChatRequest(BaseModel):
    """Request to send a message to the chatbot."""

    message: str = Field(..., min_length=1, max_length=2000)
    recent_messages: Optional[List[ChatMessage]] = Field(default=None, max_length=10)
    context_hint: Optional[str] = Field(default=None, max_length=800)
    mode: ChatMode = Field(default=ChatMode.DEFAULT)
    previous_response_id: Optional[str] = None


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


class AnswerMetadata(BaseModel):
    """Structured metadata about the sources behind an answer."""

    source_count: int = 0
    evidence_source_count: int = 0
    parliament_source_count: int = 0
    date_range: Optional[str] = None


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
        "message.delta",
    ]
    step: Optional[ChatStep] = None
    message: Optional[str] = None
    references: List[DocumentReference] = Field(default_factory=list)
    activity_summary: Optional[str] = None
    answer_metadata: Optional[AnswerMetadata] = None
    response_id: Optional[str] = None
    error: Optional[str] = None


class ChatResponse(BaseModel):
    """Response from the chatbot."""

    message: str
    references: List[DocumentReference] = Field(default_factory=list)
    steps: List[ChatStep] = Field(default_factory=list)
    activity_summary: Optional[str] = None
    answer_metadata: Optional[AnswerMetadata] = None
    response_id: Optional[str] = None
    context_used: Optional[str] = None  # For debugging
