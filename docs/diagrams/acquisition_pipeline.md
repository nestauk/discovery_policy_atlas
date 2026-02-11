# Document Acquisition and Processing Pipeline

## Overview
This diagram illustrates the pipeline for acquiring and processing documents (PDFs and HTML) from search results.

## Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         REFERENCES.CSV                                  │
│  (from search/retrieval with doc_id, pdf_url, landing_url, doi, etc.)  │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  FILTER DOCUMENTS   │
                    │  (if available)     │
                    ├──────────────────────┤
                    │ • is_relevant=true  │
                    │ • evidence_category │
                    │   != "Other"        │
                    └──────────┬───────────┘
                               │
                               ▼
        ┌──────────────────────────────────────────────┐
        │         ACQUISITION SERVICE                  │
        │  (Concurrent downloads, default: 5 at once) │
        └──────────────────┬──────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  Document 1  │   │  Document 2  │   │  Document N  │
└──────┬───────┘   └──────┬───────┘   └──────┬───────┘
       │                  │                  │
       └──────────────────┼──────────────────┘
                          │
                          ▼
        ┌─────────────────────────────────────┐
        │    DOWNLOAD STRATEGY (per doc)      │
        └─────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Try PDF URL  │  │ Try Landing   │  │ Try DOI URL  │
│ (if exists)  │  │ Page URL      │  │ (fallback)   │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │
       │                 │                 │
       ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────┐
│  PDF Download (httpx)                               │
│  • Check Content-Type: application/pdf              │
│  • Save as: {doc_id}.pdf                           │
│  • Use Referer header if available                 │
└──────────────────┬──────────────────────────────────┘
                   │ Success
                   ▼
        ┌──────────────────────┐
        │  PDF Acquired        │
        │  Save to:            │
        │  data/raw/{doc_id}.pdf│
        └──────────────────────┘
                   │
                   │ OR (if PDF fails)
                   ▼
┌─────────────────────────────────────────────────────┐
│  HTML Scraping (Scrapling or httpx+BeautifulSoup)  │
│  • Fetch HTML from landing page                    │
│  • Extract main content                            │
│  • Save HTML: {doc_id}.html                        │
│  • Save text: {doc_id}.txt                         │
└──────────────────┬──────────────────────────────────┘
                   │
                   │ Then try to discover PDF link
                   ▼
┌─────────────────────────────────────────────────────┐
│  PDF Link Discovery                                 │
│  • Parse HTML with BeautifulSoup                    │
│  • Look for <a> tags with .pdf href                 │
│  • Regex search for PDF URLs in HTML                │
│  • If found, download PDF                            │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
        ┌──────────────────────┐
        │  Files Saved         │
        │  • PDF or HTML       │
        │  • Manifest written  │
        └──────────┬───────────┘
                   │
                   ▼
        ┌─────────────────────────────────────┐
        │      PARSING SERVICE                │
        │  (Async with timeout guards)       │
        └──────────────────┬──────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  Parse PDF   │   │  Parse HTML  │   │  Skip if     │
│  (PyMuPDF)   │   │  (Scrapling/ │   │  too large   │
│              │   │   BeautifulSoup)│  │              │
└──────┬───────┘   └──────┬───────┘   └──────┬───────┘
       │                  │                  │
       │                  │                  │
       ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────┐
│  PDF Parsing                                        │
│  • Open with PyMuPDF (fitz)                        │
│  • Extract text page by page                       │
│  • Limit: MAX_PDF_PAGES (default: 50)              │
│  • Limit: MAX_TEXT_LENGTH_CHARS (default: 100k)    │
│  • Track page spans (char offsets)                 │
└──────────────────┬──────────────────────────────────┘
                   │
                   │ OR
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│  HTML Parsing                                       │
│  • Prefer: Scrapling (if available)                │
│    - Fetcher.from_file()                           │
│    - get_all_text() (ignore script/style)         │
│  • Fallback: BeautifulSoup                         │
│    - Select: article, main, #content, .content     │
│    - Extract text from matched elements            │
│  • Track page spans (single page)                  │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
        ┌──────────────────────┐
        │  ParsedText Object   │
        │  • doc_id            │
        │  • text (full text)  │
        │  • page_spans        │
        └──────────┬───────────┘
                   │
                   ▼
        ┌─────────────────────────────────────┐
        │      TEXT NORMALIZATION             │
        └──────────────────┬──────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────┐
        │  normalize_text()                   │
        │  • Remove hyphen-linebreaks (-\\n) │
        │  • Collapse multiple spaces        │
        │  • Collapse 3+ newlines to 2       │
        │  • Strip whitespace                 │
        └──────────────────┬──────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────┐
        │  Save Normalized Text               │
        │  • Path: data/normalized/{doc_id}.txt│
        │  • Ready for extraction pipeline    │
        └─────────────────────────────────────┘
```

## Key Components

### 1. Acquisition Service (`acquire.py`)
- **Input**: `references.csv` with document metadata
- **Filtering**: Only processes documents where `is_relevant=true` and `evidence_category != "Other"`
- **Concurrency**: Default 5 concurrent downloads (configurable)
- **Download Strategy**:
  1. Try PDF URL first (if available)
  2. Fallback to landing page (HTML scraping)
  3. Final fallback to DOI URL
  4. PDF link discovery from HTML (best-effort)
- **Output**: Raw files in `data/raw/` directory
- **Manifest**: Writes `manifest.jsonl` and `manifest_failures.jsonl`

### 2. Scraping (`scrape.py`)
- **Primary**: Scrapling library (if available) - robust DOM extraction
- **Fallback**: httpx + BeautifulSoup
- **Features**:
  - Handles meta refresh redirects
  - Extracts main content (article, main, #content selectors)
  - Ignores script, style, noscript tags

### 3. Parsing Service (`parse.py`)
- **PDF Parsing**:
  - Uses PyMuPDF (fitz)
  - Page-by-page text extraction
  - Guardrails: MAX_PDF_PAGES (50), MAX_PDF_SIZE_MB (50MB)
  - Truncates if exceeds limits
  - Tracks page spans for citation
- **HTML Parsing**:
  - Prefers Scrapling (if available)
  - Falls back to BeautifulSoup with content selectors
  - Extracts text from semantic HTML elements
- **Async Execution**: Runs in executor with timeout guards
- **Output**: `ParsedText` objects with text and page spans

### 4. Text Normalization (`normalize.py`)
- **Operations**:
  - De-hyphenate across line breaks (`-\n` → removed)
  - Collapse multiple spaces/tabs
  - Collapse 3+ newlines to 2 newlines
  - Strip leading/trailing whitespace
- **Output**: Clean, normalized text files in `data/normalized/`

## Configuration Limits

- **MAX_PDF_SIZE_MB**: 50.0 MB
- **MAX_PDF_PAGES**: 50 pages
- **MAX_TEXT_LENGTH_CHARS**: 100,000 characters
- **PDF_PARSE_TIMEOUT**: 30 seconds
- **HTML_PARSE_TIMEOUT**: 10 seconds
- **DOWNLOAD_TIMEOUT**: 30 seconds
- **ACQUISITION_CONCURRENCY**: 5 concurrent downloads

## Error Handling

- **Acquisition failures**: Logged to `manifest_failures.jsonl`
- **Parsing timeouts**: Caught and logged, document skipped
- **File size/page limits**: Documents truncated or skipped with warnings
- **Empty text**: Document skipped with warning
- **HTTP errors**: 401/403 handled gracefully, fallback to next URL

## Output Structure

```
export_dir/
├── data/
│   ├── raw/
│   │   ├── {doc_id}.pdf
│   │   ├── {doc_id}.html
│   │   └── {doc_id}.txt
│   ├── normalized/
│   │   └── {doc_id}.txt
│   ├── manifest.jsonl
│   └── manifest_failures.jsonl
```

## Next Steps

After normalization, documents are ready for:
- **Extraction**: LangChain workflow extracts structured data
- **Storage**: Results stored in database
- **RAG**: Text chunks embedded for vector search

