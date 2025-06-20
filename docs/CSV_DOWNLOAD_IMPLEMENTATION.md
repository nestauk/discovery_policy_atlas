# CSV Download Implementation

## Overview

This implementation adds CSV download functionality to the search results, allowing users to download their filtered and screened results as CSV files.

## Features

- ✅ **User-specific access control** - Only the user who performed the search can download their results
- ✅ **One-time downloads** - Each download link can only be used once
- ✅ **Automatic expiration** - Downloads expire after 24 hours (configurable)
- ✅ **Memory management** - Max cache size limit (100 entries) with automatic cleanup
- ✅ **File size limits** - Max 50MB per DataFrame to prevent memory issues
- ✅ **Railway-friendly cleanup** - Automatic cleanup on app startup and during requests
- ✅ **Error handling** - Proper error messages for expired or missing downloads
- ✅ **Type safety** - Full TypeScript/Python type coverage

## Architecture

### Backend Components

1. **DownloadService** (`backend/app/services/download.py`)
   - Manages in-memory cache of DataFrames (max 100 entries, 50MB each)
   - Handles user access control
   - Implements one-time downloads (removes after use)
   - Implements automatic expiration
   - Provides Railway-friendly cleanup (no background tasks)

2. **Updated Routes** (`backend/app/api/routes.py`)
   - Modified `/api/search` to return download keys
   - New `/api/download/{download_key}` endpoint for CSV downloads

3. **Models** (`backend/app/core/models.py`)
   - `SearchResultWithDownload` - Extends search results with download key
   - `DownloadCacheEntry` - Internal cache entry model

4. **Startup Cleanup** (`backend/app/main.py`)
   - Automatic cleanup of expired downloads on app startup
   - Works well with Railway's sleep/wake cycle

### Frontend Components

1. **DownloadButton** (`frontend/components/search/download-button.tsx`)
   - Handles download requests with loading states
   - Provides user feedback for errors
   - Only shows when download is available

2. **Updated Search Page** (`frontend/app/dashboard/search/page.tsx`)
   - Integrates download button with search results
   - Displays download button next to results count

3. **Updated Types** (`frontend/types/search.ts`)
   - Added `download_key` to `SearchResult` interface

## Railway Deployment Considerations

### Why No Background Tasks?

Railway puts applications to sleep when they're not receiving requests. This means:
- Background tasks stop running when the app sleeps
- When the app wakes up, there's no way to know how long it was asleep
- Background tasks can cause issues with Railway's resource management

### Railway-Friendly Cleanup Strategy

1. **Startup Cleanup**: When the app starts/wakes up, it immediately cleans expired downloads
2. **Request-Time Cleanup**: Cleanup happens automatically during search and download requests
3. **Rate-Limited Cleanup**: Prevents excessive cleanup operations (every 15 minutes max)
4. **Max Size Management**: Automatically removes oldest entries when cache reaches 100 items

## Usage

### For Users

1. Perform a search with screening enabled
2. If relevant results are found, a "Download CSV" button appears
3. Click the button to download results as CSV
4. **One-time use**: Each download link can only be used once
5. Downloads expire after 24 hours

### For Developers

#### Testing the Implementation

```bash
# Test the download service
cd backend
python test_download.py
```

#### Configuration

The download service can be configured in `DownloadService`:

```python
# In backend/app/services/download.py
download_service = DownloadService(
    expiration_hours=24,    # Change expiration time
    max_cache_size=100,     # Change max cache size
    max_file_size_mb=50     # Change max file size in MB
)
```

## Security Considerations

1. **User Isolation**: Each download key is prefixed with the user ID, preventing cross-user access
2. **One-Time Use**: Downloads are removed after first use, preventing multiple downloads
3. **Expiration**: Downloads automatically expire to prevent indefinite storage
4. **Memory Limits**: Max cache size and automatic cleanup prevent memory leaks
5. **Access Control**: Download endpoint validates user ownership
6. **No Public Endpoints**: No public endpoints for cleanup or monitoring (prevents abuse)

## Memory Management

### Cache Limits

- **Max Entries**: 100 concurrent downloads
- **Max File Size**: 50MB per DataFrame (configurable)
- **Expiration**: 24 hours (configurable)
- **Cleanup**: Automatic removal of oldest entries when limit reached
- **One-Time Use**: Entries removed immediately after download

### Memory Usage

- Each DataFrame is serialized as a Python dictionary
- Memory usage depends on DataFrame size and number of entries
- Large DataFrames (>50MB) are rejected to prevent memory issues
- Automatic cleanup prevents memory leaks
- No disk storage (by design for privacy)

## Limitations

1. **In-Memory Storage**: Data is lost on server restart (acceptable for temporary downloads)
2. **Single Server**: Not suitable for multi-instance deployments without shared cache
3. **No Persistence**: Downloads are not saved to disk (by design for privacy)
4. **Railway Sleep**: App may sleep between requests, but cleanup happens on wake-up
5. **One-Time Use**: Users cannot re-download the same results (must search again)

## Future Improvements

1. **Redis Integration**: Use Redis for shared cache across multiple server instances
2. **File Storage**: Store large downloads on disk with cleanup
3. **Download History**: Track user download history
4. **Compression**: Compress large CSV files
5. **Progress Tracking**: Show download progress for large files
6. **Multiple Downloads**: Allow users to download the same results multiple times

## Error Handling

The implementation handles these error cases:

- **404**: Download not found or expired
- **403**: User doesn't own the download
- **Network errors**: Connection issues during download
- **File errors**: Issues creating or serving the CSV file

All errors are logged and appropriate user feedback is provided. 