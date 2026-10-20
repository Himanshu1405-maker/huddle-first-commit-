"""Operator-only encrypted Huddle backup (never exposed as a public endpoint).

Run in the live Railway volume's environment under a trusted operator. To
actually protect against volume loss, configure an offsite HTTPS PUT upload URL
and schedule the script from an authorized backup worker.
"""
import argparse, gzip, io, os, sqlite3, tarfile, tempfile, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from cryptography.fernet import Fernet


def backup():
    database=Path(os.environ.get("HUDDLE_DB","./huddle.db")).resolve()
    key=os.getenv("HUDDLE_BACKUP_KEY")
    url=os.getenv("HUDDLE_BACKUP_UPLOAD_URL")
    if not key or not url:
        raise SystemExit("Backup not configured: set HUDDLE_BACKUP_KEY and HUDDLE_BACKUP_UPLOAD_URL")
    if not url.startswith("https://"):
        raise SystemExit("Backups require a private HTTPS offsite endpoint")
    if not database.is_file():
        raise SystemExit("Huddle DB path not found")
    crypto=Fernet(key.encode())
    with tempfile.TemporaryDirectory(prefix="huddle-safe-backup-") as temp:
        dest=Path(temp)/"database.sqlite3"
        source=sqlite3.connect(str(database),timeout=20)
        target=sqlite3.connect(str(dest))
        try:
            source.backup(target)
        finally:
            source.close();target.close()
        memory=io.BytesIO()
        with tarfile.open(mode="w:gz",fileobj=memory) as archive:
            archive.add(dest,arcname="huddle.sqlite3")
            media=database.parent/"media"
            if media.is_dir():
                for item in media.glob("*"):
                    if item.is_file() and item.stat().st_size<=60*1024*1024:
                        archive.add(item,arcname="media/"+item.name)
        encrypted=crypto.encrypt(memory.getvalue())
    stamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    request=urllib.request.Request(url,data=encrypted,method="PUT",
        headers={"Content-Type":"application/octet-stream",
                 "X-Huddle-Backup-Timestamp":stamp})
    with urllib.request.urlopen(request,timeout=90) as response:
        if not (200<=response.status<300):
            raise SystemExit("Offsite backup upload unsuccessful")
    print("Encrypted backup uploaded successfully. Timestamp: "+stamp+
          ". Verify restoring the backup periodically.")


if __name__=="__main__":
    backup()
