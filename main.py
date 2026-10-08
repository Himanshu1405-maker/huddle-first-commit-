"""Railpack and local single-file entrypoint for the Huddle FastAPI app.

The application implementation is in app/main.py.  This shim lets hosts
that detect a root-level main.py discover the ASGI application reliably.
"""
import os

from app.main import app

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), workers=1)
