"""
Text chunking utilities for the analysis workflow.
Implements intelligent text chunking with overlap for better RAG performance.
"""

import re
from typing import List
from dataclasses import dataclass


@dataclass
class TextChunk:
    """Represents a text chunk with metadata."""

    content: str
    chunk_index: int
    chunk_type: str
    start_char: int
    end_char: int
    token_count: int


class TextChunker:
    """
    Intelligent text chunker that respects sentence and paragraph boundaries.

    Uses best practices for RAG:
    - Target chunk size: 800-1000 tokens
    - Overlap: 100-200 tokens
    - Preserves sentence boundaries
    - Handles different content types
    """

    def __init__(
        self,
        target_tokens: int = 800,
        max_tokens: int = 1000,
        overlap_tokens: int = 150,
        min_chunk_tokens: int = 100,
    ):
        self.target_tokens = target_tokens
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        self.min_chunk_tokens = min_chunk_tokens

        # Sentence boundary detection
        self.sentence_endings = re.compile(r"[.!?]+\s+")
        self.paragraph_breaks = re.compile(r"\n\s*\n")

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count using simple word-based approximation."""
        # Rough approximation: 1 token ≈ 0.75 words
        # More accurate for academic text than pure word count
        word_count = len(text.split())
        return int(word_count * 1.3)  # Conservative estimate

    def find_good_split_point(self, text: str, target_pos: int) -> int:
        """Find the best position to split text, preferring sentence boundaries."""
        # Look for sentence endings near the target position
        search_window = 200  # characters to search around target
        start_search = max(0, target_pos - search_window)
        end_search = min(len(text), target_pos + search_window)
        search_text = text[start_search:end_search]

        # Find sentence endings in the search window
        sentence_matches = list(self.sentence_endings.finditer(search_text))

        if sentence_matches:
            # Choose the sentence ending closest to our target
            best_match = min(
                sentence_matches,
                key=lambda m: abs((start_search + m.end()) - target_pos),
            )
            return start_search + best_match.end()

        # Fallback: look for paragraph breaks
        paragraph_matches = list(self.paragraph_breaks.finditer(search_text))
        if paragraph_matches:
            best_match = min(
                paragraph_matches,
                key=lambda m: abs((start_search + m.end()) - target_pos),
            )
            return start_search + best_match.end()

        # Last resort: use word boundaries
        words = text[: target_pos + search_window].split()
        if len(words) > 0:
            return len(" ".join(words[:-1])) + 1

        return target_pos

    def chunk_text(self, text: str, chunk_type: str = "content") -> List[TextChunk]:
        """
        Chunk text into overlapping segments.

        Args:
            text: The text to chunk
            chunk_type: Type of content being chunked ("content", "abstract", "summary")

        Returns:
            List of TextChunk objects
        """
        if not text or not text.strip():
            return []

        text = text.strip()
        total_tokens = self.estimate_tokens(text)

        # If text is small enough, return as single chunk
        if total_tokens <= self.max_tokens:
            return [
                TextChunk(
                    content=text,
                    chunk_index=0,
                    chunk_type=chunk_type,
                    start_char=0,
                    end_char=len(text),
                    token_count=total_tokens,
                )
            ]

        chunks = []
        current_pos = 0
        chunk_index = 0

        while current_pos < len(text):
            # Calculate target end position based on token estimate
            chars_per_token = len(text) / total_tokens
            target_chars = int(self.target_tokens * chars_per_token)
            target_end = current_pos + target_chars

            # Don't go beyond text end
            if target_end >= len(text):
                # Last chunk - take remaining text
                chunk_content = text[current_pos:].strip()
                if (
                    chunk_content
                    and self.estimate_tokens(chunk_content) >= self.min_chunk_tokens
                ):
                    chunks.append(
                        TextChunk(
                            content=chunk_content,
                            chunk_index=chunk_index,
                            chunk_type=chunk_type,
                            start_char=current_pos,
                            end_char=len(text),
                            token_count=self.estimate_tokens(chunk_content),
                        )
                    )
                break

            # Find good split point
            split_pos = self.find_good_split_point(text, target_end)

            # Extract chunk content
            chunk_content = text[current_pos:split_pos].strip()

            if (
                chunk_content
                and self.estimate_tokens(chunk_content) >= self.min_chunk_tokens
            ):
                chunks.append(
                    TextChunk(
                        content=chunk_content,
                        chunk_index=chunk_index,
                        chunk_type=chunk_type,
                        start_char=current_pos,
                        end_char=split_pos,
                        token_count=self.estimate_tokens(chunk_content),
                    )
                )
                chunk_index += 1

            # Calculate next position with overlap
            overlap_chars = int(self.overlap_tokens * chars_per_token)
            current_pos = max(current_pos + 1, split_pos - overlap_chars)

            # Ensure we make progress
            if current_pos >= split_pos:
                current_pos = split_pos

        return chunks


def chunk_document_text(
    full_text: str = None,
    title: str = None,
    abstract: str = None,
    top_line: str = None,
    relevance_reason: str = None,
    use_abstracts_only: bool = False,
) -> List[TextChunk]:
    """
    Chunk a document into multiple types for optimal RAG performance.

    Creates:
    - Summary chunk: title + top_line + relevance (for quick overview)
    - Abstract chunk: just the abstract (for focused abstract search)
    - Content chunks: overlapping full text chunks (for detailed content)

    Returns:
        List of chunks optimized for different search scenarios
    """
    chunker = TextChunker()
    chunks = []
    chunk_index = 0

    # 1. Summary chunk (title + key findings)
    if title or top_line or relevance_reason:
        summary_parts = []
        if title:
            summary_parts.append(f"Title: {title}")
        if top_line:
            summary_parts.append(f"Key Finding: {top_line}")
        if relevance_reason:
            summary_parts.append(f"Relevance: {relevance_reason}")

        if summary_parts:
            content = "\n\n".join(summary_parts)
            chunks.append(
                TextChunk(
                    content=content,
                    chunk_index=chunk_index,
                    chunk_type="summary",
                    start_char=0,
                    end_char=len(content),
                    token_count=chunker.estimate_tokens(content),
                )
            )
            chunk_index += 1

    # 2. Abstract chunk (separate for focused abstract search)
    if abstract and abstract.strip():
        chunks.append(
            TextChunk(
                content=abstract.strip(),
                chunk_index=chunk_index,
                chunk_type="abstract",
                start_char=0,
                end_char=len(abstract),
                token_count=chunker.estimate_tokens(abstract),
            )
        )
        chunk_index += 1

    # 3. Full text chunks (if available and not abstract-only mode)
    if full_text and not use_abstracts_only and len(full_text.strip()) > 500:
        content_chunks = chunker.chunk_text(full_text, chunk_type="content")
        # Update chunk indices to continue from where we left off
        for chunk in content_chunks:
            chunk.chunk_index = chunk_index
            chunks.append(chunk)
            chunk_index += 1

    return chunks
