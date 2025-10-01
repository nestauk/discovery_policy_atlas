import pandas as pd
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional
from app.core.models import DownloadCacheEntry


class DownloadService:
    def __init__(
        self,
        expiration_hours: int = 24,
        max_cache_size: int = 100,
        max_file_size_mb: int = 50,
    ):
        self._cache: Dict[str, DownloadCacheEntry] = {}
        self.expiration_hours = expiration_hours
        self.max_cache_size = max_cache_size
        self.max_file_size_mb = max_file_size_mb
        self._last_cleanup = datetime.utcnow()

    def _estimate_dataframe_size(self, df: pd.DataFrame) -> float:
        """Estimate DataFrame size in MB"""
        # Get memory usage of DataFrame
        memory_usage = df.memory_usage(deep=True).sum()
        # Convert bytes to MB
        size_mb = memory_usage / (1024 * 1024)
        return size_mb

    def store_dataframe(
        self,
        df: pd.DataFrame,
        user_id: str,
        download_type: str,
        filename_prefix: str,
        project_id: str = None,
        query: str = None,
        custom_filename: str = None,
    ) -> str:
        """Store a DataFrame and return a download key"""
        # Clean up expired entries before storing new ones
        self._maybe_cleanup()

        # Check DataFrame size
        df_size_mb = self._estimate_dataframe_size(df)
        if df_size_mb > self.max_file_size_mb:
            raise ValueError(
                f"DataFrame too large: {df_size_mb:.2f}MB (max: {self.max_file_size_mb}MB)"
            )

        # Check if we're at max capacity and remove oldest entries if needed
        if len(self._cache) >= self.max_cache_size:
            self._remove_oldest_entries(len(self._cache) - self.max_cache_size + 1)

        # Generate unique key
        download_key = f"{user_id}_{uuid.uuid4().hex[:12]}"

        # Serialize DataFrame to dict (preserves data types)
        df_data = {
            "data": df.to_dict("records"),
            "columns": df.columns.tolist(),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        }

        # Create cache entry
        now = datetime.utcnow()
        cache_entry = DownloadCacheEntry(
            df_data=df_data,
            download_type=download_type,
            project_id=project_id,
            query=query,
            filename_prefix=filename_prefix,
            custom_filename=custom_filename,
            user_id=user_id,
            created_at=now,
            expires_at=now + timedelta(hours=self.expiration_hours),
        )

        self._cache[download_key] = cache_entry
        return download_key

    def get_dataframe(
        self, download_key: str, user_id: str
    ) -> Optional[tuple[pd.DataFrame, DownloadCacheEntry]]:
        """Retrieve a DataFrame from cache and remove it (one-time use)"""
        # Clean up expired entries before retrieving
        self._maybe_cleanup()

        if download_key not in self._cache:
            return None

        cache_entry = self._cache[download_key]

        # Check ownership
        if cache_entry.user_id != user_id:
            return None

        # Check expiration
        if datetime.utcnow() > cache_entry.expires_at:
            del self._cache[download_key]
            return None

        # Reconstruct DataFrame
        df_data = cache_entry.df_data
        df = pd.DataFrame(df_data["data"])

        # Restore column order
        if "columns" in df_data:
            df = df[df_data["columns"]]

        # Remove from cache after successful retrieval (one-time use)
        del self._cache[download_key]

        return df, cache_entry

    def _remove_oldest_entries(self, count: int):
        """Remove the oldest cache entries to make room for new ones"""
        if count <= 0:
            return

        # Sort entries by creation time and remove oldest
        sorted_entries = sorted(self._cache.items(), key=lambda x: x[1].created_at)

        for i in range(min(count, len(sorted_entries))):
            del self._cache[sorted_entries[i][0]]

    def _maybe_cleanup(self, force: bool = False) -> int:
        """Clean up expired entries if enough time has passed or if forced"""
        now = datetime.utcnow()

        # Only cleanup every 15 minutes unless forced
        if not force and (now - self._last_cleanup) < timedelta(minutes=15):
            return 0

        cleaned = self.cleanup_expired()
        self._last_cleanup = now
        return cleaned

    def cleanup_expired(self) -> int:
        """Remove expired entries and return count of cleaned items"""
        now = datetime.utcnow()
        expired_keys = [
            key for key, entry in self._cache.items() if now > entry.expires_at
        ]

        for key in expired_keys:
            del self._cache[key]

        return len(expired_keys)

    def force_cleanup(self) -> int:
        """Force cleanup of expired entries (useful when app wakes up)"""
        return self._maybe_cleanup(force=True)

    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics"""
        # Clean up before getting stats
        self._maybe_cleanup()

        now = datetime.utcnow()
        expired_count = sum(
            1 for entry in self._cache.values() if now > entry.expires_at
        )

        return {
            "total_entries": len(self._cache),
            "expired_entries": expired_count,
            "active_entries": len(self._cache) - expired_count,
            "max_cache_size": self.max_cache_size,
            "max_file_size_mb": self.max_file_size_mb,
            "last_cleanup": self._last_cleanup.isoformat(),
        }


# Global instance with max 100 entries and 50MB file size limit
download_service = DownloadService(max_cache_size=100, max_file_size_mb=50)
