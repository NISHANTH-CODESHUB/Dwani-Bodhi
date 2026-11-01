"""Blob storage abstraction: local disk (dev / single VM) or any S3-compatible store (scale-out)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol

from .config import get_settings


class BlobStore(Protocol):
    def put(self, key: str, data: bytes, mime: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class LocalBlobStore:
    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root.resolve() not in p.parents:
            raise ValueError("invalid blob key")
        return p

    def put(self, key: str, data: bytes, mime: str) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3BlobStore:  # pragma: no cover - exercised in deployment
    def __init__(self, bucket: str, endpoint: str | None) -> None:
        import boto3

        self.bucket = bucket
        self.s3 = boto3.client("s3", endpoint_url=endpoint)

    def put(self, key: str, data: bytes, mime: str) -> None:
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=mime, ServerSideEncryption="AES256")

    def get(self, key: str) -> bytes:
        try:
            return self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except self.s3.exceptions.NoSuchKey as e:  # same contract as the local store
            raise FileNotFoundError(key) from e

    def delete(self, key: str) -> None:
        self.s3.delete_object(Bucket=self.bucket, Key=key)


_store: BlobStore | None = None


def get_store() -> BlobStore:
    global _store
    if _store is None:
        s = get_settings()
        _store = S3BlobStore(s.s3_bucket or "", s.s3_endpoint) if s.blob_backend == "s3" else LocalBlobStore(s.blob_dir)
    return _store


def reset_store() -> None:
    global _store
    _store = None


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
