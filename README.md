# AI Image Upscaler

An imgupscaler.com-style web app: drop in one image or a whole batch, choose
**200%** or **400%**, and download the results one by one or as a ZIP.

| Part | Tech |
|---|---|
| AI model | [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN): `RealESRGAN_x2plus` (200%), `RealESRGAN_x4plus` (400%) |
| Inference | PyTorch + [spandrel](https://github.com/chaiNNer-org/spandrel), tiled so large images fit in GPU memory, fp16 on CUDA |
| API | FastAPI + Uvicorn, Pillow, in-process job queue with one worker |
| Frontend | React + Vite + TypeScript + Tailwind CSS, react-dropzone |

## Running locally

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate

# Install PyTorch for your hardware first:
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124   # NVIDIA GPU
# pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu   # CPU only

pip install -r requirements-dev.txt
python scripts/download_models.py        # ~130 MB, into backend/models/
uvicorn app.main:app --port 8000
```

`GET http://localhost:8000/api/health` reports which upscaler loaded. If the
model files are missing, the server falls back to plain Lanczos resizing so
the rest of the app still works.

### Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173, proxies /api to localhost:8000
```

For production, `npm run build` produces static files in `frontend/dist/`.
Serve them from any static host and set `VITE_API_URL` at build time if the
API is on another origin (also add that origin to the backend's `CORS_ORIGINS`).

## API

| Method & path | Purpose |
|---|---|
| `POST /api/jobs` | multipart `files` (one or more) + `scale` (`2` or `4`); returns the job |
| `GET /api/jobs/{id}` | job and per-file status (`queued`, `processing`, `done`, `error`) and progress |
| `GET /api/jobs/{id}/files/{file_id}` | upscaled image (same format as the upload) |
| `GET /api/jobs/{id}/original/{file_id}` | original upload (used by the before/after slider) |
| `GET /api/jobs/{id}/zip` | ZIP of all finished images |
| `GET /api/config` | upload limits, for the UI |

## Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `MAX_FILE_MB` | 10 | max size per upload |
| `MAX_FILES_PER_JOB` | 20 | max images per batch |
| `MAX_INPUT_SIDE_2X` / `MAX_INPUT_SIDE_4X` | 4096 / 2048 | longest input side allowed per scale |
| `TILE_SIZE` / `TILE_OVERLAP` | 512 / 32 | inference tile size; lower `TILE_SIZE` if the GPU runs out of memory |
| `JOB_TTL_SECONDS` | 3600 | finished jobs and their files are deleted after this |
| `CORS_ORIGINS` | `http://localhost:5173` | comma-separated allowed origins |
| `MODELS_DIR` / `STORAGE_DIR` | `backend/models` / `backend/storage` | |

## Performance

On CPU a 120×90 image takes a few seconds at 4x; megapixel photos take
minutes. For real traffic, run the backend on a machine with an NVIDIA GPU
(for example AWS g4dn/g5, RunPod or Lambda), which is many times faster.

The job queue and job state live in memory, so run a single API process. To
scale out, move them to Redis plus a worker pool, and the files to object storage.

## Tests

```bash
cd backend && pytest
```

The tests swap in the Lanczos upscaler, so they need neither a GPU nor model weights.
