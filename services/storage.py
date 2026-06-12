"""
storage.py — Object storage abstraction for user-uploaded files.

Two backends, selected by STORAGE_BACKEND:
  * "local" — files under LOCAL_STORAGE_DIR (dev, no infra).
  * "s3"    — any S3-compatible store (AWS S3, GCS interop, minio) via boto3.

Keys are tenant-scoped so one bucket safely holds every tenant's uploads:
    tenants/<tenant_id>/uploads/<file_id>_<name>

The rest of the app deals only in storage keys; `local_path_for()` materializes
a key to a temp file on demand for libraries that need a filesystem path
(Telegram send_document, Drive MediaFileUpload).
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Optional

from services.config import settings
from services.tenancy import current_tenant_id

logger = logging.getLogger(__name__)

_s3_client = None


def _is_s3() -> bool:
    return settings.storage_backend.lower() == "s3"


def tenant_key(name: str) -> str:
    """Build a tenant-scoped object key for an upload."""
    return f"tenants/{current_tenant_id()}/uploads/{name}"


# ---------------------------------------------------------------------------
# S3 backend
# ---------------------------------------------------------------------------

def _client():
    global _s3_client
    if _s3_client is None:
        import boto3

        _s3_client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url or None,
            region_name=settings.s3_region,
        )
    return _s3_client


# ---------------------------------------------------------------------------
# Local backend
# ---------------------------------------------------------------------------

def _local_path(key: str) -> str:
    path = os.path.join(settings.local_storage_dir, key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def put_file(local_path: str, key: str, content_type: str = "") -> str:
    with open(local_path, "rb") as f:
        return put_bytes(f.read(), key, content_type)


def put_bytes(data: bytes, key: str, content_type: str = "") -> str:
    if _is_s3():
        extra = {"ContentType": content_type} if content_type else {}
        _client().put_object(Bucket=settings.s3_bucket, Key=key, Body=data, **extra)
    else:
        with open(_local_path(key), "wb") as f:
            f.write(data)
    return key


def get_bytes(key: str) -> Optional[bytes]:
    try:
        if _is_s3():
            obj = _client().get_object(Bucket=settings.s3_bucket, Key=key)
            return obj["Body"].read()
        path = _local_path(key)
        if not os.path.exists(path):
            return None
        with open(path, "rb") as f:
            return f.read()
    except Exception as e:
        logger.error("storage.get_bytes failed for %s: %s", key, e)
        return None


def exists(key: str) -> bool:
    if _is_s3():
        try:
            _client().head_object(Bucket=settings.s3_bucket, Key=key)
            return True
        except Exception:
            return False
    return os.path.exists(_local_path(key))


def delete(key: str) -> None:
    try:
        if _is_s3():
            _client().delete_object(Bucket=settings.s3_bucket, Key=key)
        else:
            path = _local_path(key)
            if os.path.exists(path):
                os.remove(path)
    except Exception as e:
        logger.warning("storage.delete failed for %s: %s", key, e)


def local_path_for(key: str, suffix: str = "") -> Optional[str]:
    """Return a filesystem path holding the object's bytes.

    For the local backend this is the file itself; for S3 it downloads to a
    temp file. Returns None if the object is missing.
    """
    if not _is_s3():
        path = _local_path(key)
        return path if os.path.exists(path) else None
    data = get_bytes(key)
    if data is None:
        return None
    fd, tmp = tempfile.mkstemp(suffix=suffix or os.path.splitext(key)[1])
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return tmp
