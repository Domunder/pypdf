# openwebui-loaders

An OpenWebUI-compatible **External Content Extraction Engine** that runs all of
LangChain's document loaders as a standalone microservice.

Supported formats: PDF, DOCX, XLSX, PPTX, CSV, XML, HTML, Markdown, EPUB, ODT, RST, MSG, and plain-text / source-code files.

---

## Build & push
```bash
docker buildx build --platform linux/amd64 -t hatchet8513/openwebui-loaders:1.0.0 --push .
```

---

## Deploy to OpenShift
```bash
oc project <your-namespace>
oc new-app your-registry.example.com/openwebui-loaders:1.0.0
oc expose svc/openwebui-loaders
oc rollout status deployment/openwebui-loaders
```

---

## Configure OpenWebUI

**Admin → Settings → Documents**

| Field | Value |
|---|---|
| Content Extraction Engine | `External` |
| Extraction Engine URL | `http://openwebui-loaders.<namespace>.svc.cluster.local` |
| Extraction Engine API Key | *(`secret`, or set if `API_KEY` is configured)* |

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `API_KEY` | `secret` | Bearer token for auth; leave empty to disable |
| `MAX_FILE_SIZE_MB` | `100` | Upload size limit |
| `TASK_TIMEOUT` | `60` | Max seconds per extraction before 504 |
| `PDF_LOADER_MODE` | `single` | `page` = one doc per page, `single` = whole file as one doc |
| `PDF_EXTRACT_IMAGES` | `false` | Enable image OCR (requires `rapidocr-onnxruntime`) |
| `PORT` | `5001` | Listening port |
| `WORKERS` | `4` | Uvicorn worker count |

---

## API

### `GET /health`
Liveness probe. Returns `{"status": "ok"}`.

### `PUT /process`
OpenWebUI sends a raw binary body with the filename in the `X-Filename` header.
The service also accepts `multipart/form-data` (field name `file`) for local testing.
Returns a JSON array:
```json
[
  { "page_content": "...", "metadata": { "source": "file.pdf" } }
]
```

---

## Local testing
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --port 5001

# multipart (local test)
curl -X PUT http://localhost:5001/process \
     -F "file=@sample.pdf" | python -m json.tool

# raw binary (mirrors how OpenWebUI calls it)
curl -X PUT http://localhost:5001/process \
     -H "X-Filename: sample.pdf" \
     -H "Content-Type: application/pdf" \
     --data-binary @sample.pdf | python -m json.tool
```

---

## Keeping loaders in sync with OpenWebUI

OpenWebUI's internal loader logic lives in:
```
backend/open_webui/retrieval/loaders/main.py
```

Inside that file, find the class `Loader` and its `_get_loader` method. This method maps file extensions and MIME types to specific LangChain loader classes. Whenever OpenWebUI adds support for a new file format, it will appear there first.

To keep this microservice in sync:

1. Open `backend/open_webui/retrieval/loaders/main.py` in the OpenWebUI repository.
2. Find the `_get_loader` method inside the `Loader` class.
3. Compare it with the `_get_loader` function in `app.py` of this repo.
4. Copy any new `if` branches (new file extensions or MIME types) into `app.py`.
5. Add any newly required LangChain loader imports at the top of `app.py`.
6. Add any new dependencies to `requirements.txt` and rebuild the image.

The mapping pattern is always the same — check the extension or MIME type, return the appropriate loader instance — so porting new entries is straightforward.