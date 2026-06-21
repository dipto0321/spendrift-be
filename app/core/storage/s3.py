"""S3-compatible storage backend (Cloudflare R2, MinIO, Floci, AWS S3)."""

import boto3
from botocore.config import Config


class S3StorageBackend:
    def __init__(
        self,
        endpoint_url: str,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
    ) -> None:
        self._bucket = bucket_name
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            # "auto" works for R2; harmless for MinIO/Floci
            region_name="auto",
            config=Config(signature_version="s3v4"),
        )

    def upload(self, file_key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=file_key,
            Body=data,
            ContentType=content_type,
        )

    def delete(self, file_key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=file_key)

    def generate_presigned_url(self, file_key: str, expires_in: int) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": file_key},
            ExpiresIn=expires_in,
        )
