"""Blob storage abstraction: local disk (dev / single VM), any S3-compatible store (scale-out), or the
database itself (serverless hosts with no persistent disk, e.g. Vercel + Postgres)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from .config import get_settings

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


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


class DbBlobStore:
    """Bytes in the `blob_data` table, inside the caller's transaction: a media row and its bytes commit
    (or roll back) together. Media is small and short-lived (audio <= 2 MB, deleted after scoring/review;
    classroom photos deleted after cropping), so this suits pilot-scale serverless deploys."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def put(self, key: str, data: bytes, mime: str) -> None:
        from .models import BlobData

        self.db.merge(BlobData(key=key, data=data, mime=mime))
        self.db.flush()

    def get(self, key: str) -> bytes:
        from .models import BlobData

        row = self.db.get(BlobData, key)
        if row is None:
            raise FileNotFoundError(key)
        return bytes(row.data)

    def delete(self, key: str) -> None:
        from sqlalchemy import delete

        from .models import BlobData

        self.db.execute(delete(BlobData).where(BlobData.key == key))


_store: BlobStore | None = None


def get_store(db: Session) -> BlobStore:
    """The configured store. `db` is the caller's session (used by the database backend)."""
    global _store
    s = get_settings()
    if s.blob_backend == "db":
        return DbBlobStore(db)
    if _store is None:
        _store = S3BlobStore(s.s3_bucket or "", s.s3_endpoint) if s.blob_backend == "s3" else LocalBlobStore(s.blob_dir)
    return _store


def reset_store() -> None:
    global _store
    _store = None


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
