"""Rotate only the target application's JWT signing secret, without printing it."""

from datetime import datetime, timezone
from pathlib import Path
import secrets
import shutil

from dotenv import set_key

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    source = ROOT / "backend/.env"
    backup = ROOT / ".local/backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(source, backup / "backend.env")
    set_key(source, "JWT_SECRET", secrets.token_urlsafe(48))
    print("Target JWT rotated. Previous learning tokens are invalid. Backup is private.")
