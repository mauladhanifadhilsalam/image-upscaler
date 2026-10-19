from __future__ import annotations

import io
import logging
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from . import config
from .jobs import JobManager
from .upscaler import Upscaler, load_upscaler

logging.basicConfig(level=logging.INFO)

MEDIA_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


def create_app(upscaler: Upscaler | None = None, storage_dir: Path = config.STORAGE_DIR) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        manager = JobManager(upscaler or await run_in_threadpool(load_upscaler), storage_dir)
        manager.start()
        app.state.manager = manager
        yield
        manager.stop()

    app = FastAPI(title="Image Upscaler", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def manager() -> JobManager:
        return app.state.manager

    def get_job(job_id: str):
        job = manager().get(job_id)
        if job is None:
            raise HTTPException(404, "Job not found or expired")
        return job

    @app.get("/api/health")
    def health():
        return {"status": "ok", "upscaler": manager().upscaler.name, "scales": list(config.SUPPORTED_SCALES)}

    @app.get("/api/config")
    def limits():
        return {
            "scales": list(config.SUPPORTED_SCALES),
            "max_file_bytes": config.MAX_FILE_BYTES,
            "max_files": config.MAX_FILES_PER_JOB,
            "max_input_side": config.MAX_INPUT_SIDE,
            "formats": sorted(MEDIA_TYPES.values()),
        }

    @app.post("/api/jobs", status_code=201)
    async def create_job(files: list[UploadFile] = File(...), scale: int = Form(...)):
        if scale not in config.SUPPORTED_SCALES:
            raise HTTPException(422, f"scale must be one of {list(config.SUPPORTED_SCALES)}")
        if len(files) > config.MAX_FILES_PER_JOB:
            raise HTTPException(422, f"At most {config.MAX_FILES_PER_JOB} files per batch")

        uploads = []
        for upload in files:
            name = upload.filename or "image"
            data = await upload.read(config.MAX_FILE_BYTES + 1)
            if len(data) > config.MAX_FILE_BYTES:
                raise HTTPException(413, f"{name} is larger than {config.MAX_FILE_BYTES // (1024 * 1024)} MB")
            try:
                image = Image.open(io.BytesIO(data))
            except UnidentifiedImageError:
                raise HTTPException(415, f"{name} is not a supported image")
            if image.format not in config.ALLOWED_FORMATS:
                raise HTTPException(415, f"{name}: only JPG, PNG and WEBP are supported")
            limit = config.MAX_INPUT_SIDE[scale]
            if max(image.size) > limit:
                raise HTTPException(
                    422, f"{name} is {image.width}x{image.height}; the longest side must be at most {limit}px for {scale}x"
                )
            uploads.append((name, data, image))

        job = await run_in_threadpool(manager().create_job, scale, uploads)
        return job.to_dict()

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str):
        return get_job(job_id).to_dict()

    @app.get("/api/jobs/{job_id}/files/{file_id}")
    def download_file(job_id: str, file_id: str):
        item = get_job(job_id).file(file_id)
        if item is None:
            raise HTTPException(404, "File not found")
        if item.status != "done":
            raise HTTPException(409, f"File is {item.status}")
        return FileResponse(item.output_path, media_type=MEDIA_TYPES[item.format], filename=item.output_name)

    @app.get("/api/jobs/{job_id}/original/{file_id}")
    def original_file(job_id: str, file_id: str):
        item = get_job(job_id).file(file_id)
        if item is None:
            raise HTTPException(404, "File not found")
        return FileResponse(item.original_path, media_type=MEDIA_TYPES[item.format])

    @app.get("/api/jobs/{job_id}/zip")
    def download_zip(job_id: str):
        job = get_job(job_id)
        done = [f for f in job.files if f.status == "done"]
        if not done:
            raise HTTPException(409, "No finished files yet")
        path = job.dir / "upscaled.zip"
        used: set[str] = set()
        # Outputs are already compressed images, so store them as-is.
        with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as archive:
            for item in done:
                name, n = item.output_name, 1
                while name in used:
                    stem, ext = Path(item.output_name).stem, Path(item.output_name).suffix
                    name, n = f"{stem} ({n}){ext}", n + 1
                used.add(name)
                archive.write(item.output_path, name)
        return FileResponse(path, media_type="application/zip", filename=f"upscaled_{job.scale}x.zip")

    return app


app = create_app()
