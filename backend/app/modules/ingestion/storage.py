import re
import uuid
from pathlib import Path

from fastapi import UploadFile


SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


async def persist_upload(upload: UploadFile, storage_root: Path) -> Path:
    """Persist the original upload before parsing so evidence can always reference it."""
    original_name = Path(upload.filename or "upload").name
    safe_name = SAFE_FILENAME.sub("_", original_name)
    destination = storage_root / f"{uuid.uuid4()}_{safe_name}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    too_large = False
    with destination.open("wb") as target:
        while chunk := await upload.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                too_large = True
                break
            target.write(chunk)
    await upload.close()
    if too_large:
        destination.unlink(missing_ok=True)
        raise ValueError("Uploaded file exceeds the 25 MB limit.")
    return destination
