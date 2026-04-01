import asyncio
import logging
import os
import time
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import ftfy
from fastapi import FastAPI, File, Header, HTTPException, UploadFile, Request
from fastapi.responses import JSONResponse
from langchain_community.document_loaders import (
    BSHTMLLoader,
    CSVLoader,
    Docx2txtLoader,
    OutlookMessageLoader,
    PyPDFLoader,
    TextLoader,
    UnstructuredEPubLoader,
    UnstructuredExcelLoader,
    UnstructuredODTLoader,
    UnstructuredPowerPointLoader,
    UnstructuredRSTLoader,
    UnstructuredXMLLoader,
)
from langchain_core.documents import Document

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
API_KEY = os.getenv("API_KEY", "secret")
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "100"))
TASK_TIMEOUT = int(os.getenv("TASK_TIMEOUT", "60"))
PDF_EXTRACT_IMAGES = os.getenv("PDF_EXTRACT_IMAGES", "false").lower() == "true"
PDF_LOADER_MODE = os.getenv("PDF_LOADER_MODE", "single")
THREAD_WORKERS = int(os.getenv("THREAD_WORKERS", "4"))

# executor will be initialized at startup
_executor: ThreadPoolExecutor | None = None

# ---------------------------------------------------------------------------
# Known source-code / plain-text extensions
# ---------------------------------------------------------------------------
KNOWN_SOURCE_EXT = {
    "go", "py", "java", "sh", "bat", "ps1", "cmd", "js", "ts", "css",
    "cpp", "hpp", "h", "c", "cs", "sql", "log", "ini", "pl", "pm", "r",
    "dart", "dockerfile", "env", "php", "hs", "hsc", "lua", "nginxconf",
    "conf", "m", "mm", "plsql", "perl", "rb", "rs", "db2", "scala",
    "bash", "swift", "vue", "svelte", "ex", "exs", "erl", "tsx", "jsx",
    "lhs", "json",
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("openwebui-loaders")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="OpenWebUI Document Loaders", version="3.0.0")


@app.on_event("startup")
def startup_executor():
    global _executor
    _executor = ThreadPoolExecutor(max_workers=THREAD_WORKERS)
    log.info(f"{time.localtime()} ThreadPoolExecutor started with {THREAD_WORKERS} workers")


@app.on_event("shutdown")
def shutdown_executor():
    global _executor
    if _executor:
        _executor.shutdown(wait=False)
        log.info(f"{time.localtime()} ThreadPoolExecutor shut down")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    log.info(f"{time.localtime()} {request.method} {request.url}")
    response = await call_next(request)
    return response


@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Helper: pick the right loader
# ---------------------------------------------------------------------------
def _get_loader(filename: str, file_content_type: str, file_path: str):
    file_ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if file_ext == "pdf":
        return PyPDFLoader(
            file_path,
            extract_images=PDF_EXTRACT_IMAGES,
            mode=PDF_LOADER_MODE,
        )

    if file_ext == "csv":
        return CSVLoader(file_path, autodetect_encoding=True)

    if file_ext == "rst":
        return UnstructuredRSTLoader(file_path, mode="elements")

    if file_ext == "xml":
        return UnstructuredXMLLoader(file_path)

    if file_ext in ("htm", "html"):
        return BSHTMLLoader(file_path, open_encoding="unicode_escape")

    if file_ext == "md":
        return TextLoader(file_path, autodetect_encoding=True)

    if file_content_type == "application/epub+zip":
        return UnstructuredEPubLoader(file_path)

    if (
        file_content_type
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        or file_ext == "docx"
    ):
        return Docx2txtLoader(file_path)

    if file_content_type in (
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ) or file_ext in ("xls", "xlsx"):
        return UnstructuredExcelLoader(file_path)

    if file_content_type in (
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ) or file_ext in ("ppt", "pptx"):
        return UnstructuredPowerPointLoader(file_path)

    if file_ext == "msg":
        return OutlookMessageLoader(file_path)

    if file_ext == "odt":
        return UnstructuredODTLoader(file_path)

    return TextLoader(file_path, autodetect_encoding=True)


# ---------------------------------------------------------------------------
# Sync extraction (runs in executor)
# ---------------------------------------------------------------------------
def _extract(file_path: str, filename: str, file_content_type: str) -> list[Document]:
    loader = _get_loader(filename, file_content_type, file_path)
    docs = loader.load()

    fixed = []
    for doc in docs:
        doc.metadata.setdefault("source", filename)
        fixed.append(
            Document(
                page_content=ftfy.fix_text(doc.page_content),
                metadata=doc.metadata,
            )
        )
    return fixed


# ---------------------------------------------------------------------------
# /process endpoint
# ---------------------------------------------------------------------------
@app.put("/process")
async def process(
    request: Request,
    authorization: str = Header(default=""),
):
    if API_KEY:
        token = authorization.replace("Bearer ", "").strip() if authorization else ""
        if token != API_KEY:
            log.warning(f'{time.localtime()} Unauthorized access attempt')
            raise HTTPException(status_code=401, detail="Unauthorized")

    content_type = request.headers.get("Content-Type", "")
    
    # Handle multipart (your test script) vs raw binary (Open WebUI)
    if "multipart/form-data" in content_type:
        form = await request.form()
        file_field = form.get("file")
        if file_field is None:
            raise HTTPException(status_code=400, detail="No file field in form")
        filename = file_field.filename or "upload"
        file_content_type = file_field.content_type or "application/octet-stream"
        body = await file_field.read()
    else:
        # Raw binary — Open WebUI style
        from urllib.parse import unquote
        filename = unquote(request.headers.get("X-Filename", "upload"))
        file_content_type = content_type or "application/octet-stream"
        body = await request.body()

    size = len(body)
    if size > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large")

    suffix = Path(filename).suffix or ".bin"
    tmp_path: str | None = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
            tmp.write(body)

        log.info(f"{time.localtime()} Processing '%s' (%s, %.1f KB)", filename, file_content_type, size / 1024)

        try:
            loop = asyncio.get_running_loop()
            if _executor is None:
                raise HTTPException(status_code=500, detail="Executor not initialized")

            docs = await asyncio.wait_for(
                loop.run_in_executor(
                    _executor, _extract, tmp_path, filename, file_content_type
                ),
                timeout=TASK_TIMEOUT,
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail=f"Extraction timed out after {TASK_TIMEOUT}s")
        except Exception:
            log.exception(f"{time.localtime()} Extraction failed for '%s'", filename)
            raise HTTPException(status_code=500, detail="Extraction failed")

        return JSONResponse(
            content=[
                {"page_content": d.page_content, "metadata": d.metadata}
                for d in docs
            ]
        )

    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass