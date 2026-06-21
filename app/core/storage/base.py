"""Storage backend protocol — swap implementations without touching business logic."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class StorageBackend(Protocol):
    def upload(self, file_key: str, data: bytes, content_type: str) -> None: ...

    def delete(self, file_key: str) -> None: ...

    def generate_presigned_url(self, file_key: str, expires_in: int) -> str: ...
