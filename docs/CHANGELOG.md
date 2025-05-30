# Changelog

## [Unreleased] - 2025-05-30

### Added
- MediaCloud (News) search support, including scraping and LLM summarization for missing abstracts.
- Extraction fields and inclusion criteria in advanced search options.
- AI Screening toggle (checkbox) in the search form, with backend support.
- AI summary generation for search results, with a dedicated endpoint and frontend component.
- Improved UI for source selection ("Research" and "News") and advanced options.

### Changed
- Refactored backend to support both OpenAlex and MediaCloud sources.
- Updated frontend to allow dynamic extraction fields and inclusion criteria.
- Enhanced result cards to display extracted fields.

### Fixed
- Bug where AI screening toggle was not respected by the backend.

### Dependencies
- Added `scrapling` for web scraping.
- Ensure `mediacloud` and LLM dependencies are installed and configured. 