"""Storage factory — returns the configured backend as a FastAPI dependency."""

from functools import lru_cache

from app.core.config import settings
from app.core.storage.s3 import S3StorageBackend


@lru_cache(maxsize=1)
def _build_storage() -> S3StorageBackend:
    return S3StorageBackend(
        endpoint_url=settings.storage_endpoint_url,
        access_key_id=settings.storage_access_key_id,
        secret_access_key=settings.storage_secret_access_key,
        bucket_name=settings.storage_bucket_name,
    )


def get_storage() -> S3StorageBackend:
    """FastAPI dependency that returns the singleton storage backend."""
    return _build_storage()
