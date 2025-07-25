# Search Components

This directory contains components for displaying search results in different formats.

## PapersTable Component

The `PapersTable` component provides an interactive table view for search results using Ant Design's Table component.

### Features

- **Sortable Columns**: Click column headers to sort by title, year, citations, etc.
- **Filterable Columns**: Use the filter dropdowns to filter by relevance, source type, etc.
- **Search Functionality**: Global search across all columns
- **Pagination**: Navigate through large result sets
- **Responsive Design**: Horizontal scrolling for mobile devices
- **Visual Indicators**: 
  - Relevant papers are highlighted with green background
  - High citation counts are highlighted in green
  - Source types are color-coded with tags

### Columns

1. **Title**: Clickable links to papers, with relevance badge
2. **Authors**: Displayed as tags, shows first 2 authors + count
3. **Year**: Sortable publication year
4. **Citations**: Sortable citation count with highlighting for high-impact papers
5. **Source**: Academic vs Policy documents with country/source type tags
6. **Topics**: Policy topics as purple tags
7. **Relevance**: AI screening results with confidence scores
8. **Actions**: Quick access to view papers

### Usage

```tsx
import { PapersTable } from '@/components/search/papers-table'

<PapersTable 
  papers={searchResults.papers} 
  onDownload={() => handleDownload()}
/>
```

## ViewToggle Component

The `ViewToggle` component allows users to switch between card and table views.

### Usage

```tsx
import { ViewToggle } from '@/components/search/view-toggle'

<ViewToggle 
  currentView={viewMode} 
  onViewChange={setViewMode} 
/>
```

## Integration

Both components are integrated into the main search page (`/dashboard/search`) and can be toggled using the view toggle buttons. 