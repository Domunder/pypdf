import asyncio
import logging
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Header, HTTPException, UploadFile, Request
from fastapi.responses import JSONResponse
from langchain_community.document_loaders import PyPDFLoader

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
API_KEY = os.getenv("API_KEY", "")
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "20"))
TASK_TIMEOUT = int(os.getenv("TASK_TIMEOUT", "60"))
ALLOWED_TYPES = {"application/pdf"}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("pypdf-extractor")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="PyPDF Extractor", version="2.0.0")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    log.info(f"{request.method} {request.url}")
    response = await call_next(request)
    return response


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/process")
async def process(
    file: UploadFile = File(...),
    authorization: str = Header(default=""),
):
    # --- Auth ---
    if API_KEY:
        token = authorization.replace("Bearer ", "") if authorization else ""
        if token != API_KEY:
            raise HTTPException(status_code=401, detail="Unauthorized")

    # --- Validate content type ---
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Only PDF files allowed")

    # --- Stream upload into temp file, enforcing size limit ---
    size = 0
    suffix = Path(file.filename or "upload.pdf").suffix or ".pdf"
    tmp_path: str | None = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
            while chunk := await file.read(1024 * 1024):  # 1 MB chunks
                size += len(chunk)
                if size > MAX_FILE_SIZE_MB * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="File too large")
                tmp.write(chunk)

        # --- Extract with timeout ---
        try:
            docs = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, _extract, tmp_path, file.filename or "upload.pdf"
                ),
                timeout=TASK_TIMEOUT,
            )
        except asyncio.TimeoutError:
            log.warning("Extraction timed out after %ds for %s", TASK_TIMEOUT, file.filename)
            raise HTTPException(status_code=504, detail=f"Extraction timed out after {TASK_TIMEOUT}s")
        except Exception:
            log.exception("Extraction failed for %s", file.filename)
            raise HTTPException(status_code=500, detail="Extraction failed")

        return JSONResponse(content={
            "documents": [
                {"page_content": d.page_content, "metadata": d.metadata}
                for d in docs
            ]
        })

    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _extract(file_path: str, filename: str):
    loader = PyPDFLoader(file_path, mode="single")
    docs = loader.load()
    for d in docs:
        d.metadata["source"] = filename
    return docs