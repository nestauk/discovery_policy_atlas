"""
Pydantic models for chatbot service.
"""

from pydantic import BaseModel, Field
from typing import List, Optional
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


class ChatResponse(BaseModel):
    """Response from the chatbot."""

    message: str
    references: List[DocumentReference] = Field(default_factory=list)
    context_used: Optional[str] = None  # For debugging
