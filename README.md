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
| Extraction Engine API Key | *(leave blank, or set if `API_KEY` is configured)* |

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

### `POST /process`
Multipart upload — field name `file`. Returns:
```json
{
  "documents": [
    { "page_content": "...", "metadata": { "source": "file.pdf" } }
  ]
}
```

---

## Local testing

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --port 5001

curl -X POST http://localhost:5001/process \
     -F "file=@sample.pdf" | python -m json.tool
```