"""In-memory job registry with a single background worker.

The GPU processes one image at a time, so a thread draining a queue is all
the scheduling an MVP needs. Jobs and their files are dropped after a TTL.
"""

from __future__ import annotations

import logging
import queue
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from . import config
from .upscaler import Upscaler

log = logging.getLogger(__name__)

EXTENSIONS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}


@dataclass
class FileItem:
    id: str
    name: str
    format: str
    width: int
    height: int
    original_path: Path
    output_path: Path | None = None
    output_name: str | None = None
    status: str = "queued"  # queued | processing | done | error
    progress: float = 0.0
    error: str | None = None

    def to_dict(self, scale: int) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "output_name": self.output_name,
            "status": self.status,
            "progress": round(self.progress, 3),
            "error": self.error,
            "width": self.width,
            "height": self.height,
            "output_width": self.width * scale,
            "output_height": self.height * scale,
        }


@dataclass
class Job:
    id: str
    scale: int
    dir: Path
    files: list[FileItem] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    @property
    def status(self) -> str:
        statuses = {f.status for f in self.files}
        if statuses <= {"done", "error"}:
            return "done"
        if statuses == {"queued"}:
            return "queued"
        return "processing"

    def file(self, file_id: str) -> FileItem | None:
        return next((f for f in self.files if f.id == file_id), None)

    def to_dict(self) -> dict:
        progress = sum(1.0 if f.status in ("done", "error") else f.progress for f in self.files)
        return {
            "id": self.id,
            "scale": self.scale,
            "status": self.status,
            "progress": round(progress / len(self.files), 3) if self.files else 1.0,
            "files": [f.to_dict(self.scale) for f in self.files],
        }


def output_name(original: str, scale: int, fmt: str) -> str:
    stem = Path(original).stem or "image"
    return f"{stem}_{scale}x.{EXTENSIONS[fmt]}"


class JobManager:
    def __init__(self, upscaler: Upscaler, storage_dir: Path = config.STORAGE_DIR):
        self.upscaler = upscaler
        self.storage_dir = storage_dir
        self.jobs: dict[str, Job] = {}
        self._queue: queue.Queue[tuple[Job, FileItem] | None] = queue.Queue()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        for target in (self._worker, self._cleanup_loop):
            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            self._threads.append(thread)

    def stop(self) -> None:
        self._stop.set()
        self._queue.put(None)
        for thread in self._threads:
            thread.join(timeout=5)

    def create_job(self, scale: int, uploads: list[tuple[str, bytes, Image.Image]]) -> Job:
        job_id = uuid.uuid4().hex
        job = Job(id=job_id, scale=scale, dir=self.storage_dir / job_id)
        (job.dir / "in").mkdir(parents=True)
        (job.dir / "out").mkdir()
        for name, data, image in uploads:
            item_id = uuid.uuid4().hex[:12]
            path = job.dir / "in" / f"{item_id}.{EXTENSIONS[image.format]}"
            path.write_bytes(data)
            job.files.append(FileItem(
                id=item_id, name=name, format=image.format,
                width=image.width, height=image.height, original_path=path,
            ))
        with self._lock:
            self.jobs[job_id] = job
        for item in job.files:
            self._queue.put((job, item))
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self.jobs.get(job_id)

    def _worker(self) -> None:
        while not self._stop.is_set():
            task = self._queue.get()
            if task is None:
                break
            job, item = task
            if self.get(job.id) is None:
                continue  # expired before it was processed
            self._process(job, item)

    def _process(self, job: Job, item: FileItem) -> None:
        item.status = "processing"

        def report(fraction: float) -> None:
            item.progress = fraction

        try:
            with Image.open(item.original_path) as image:
                image.load()
                result = self.upscaler.upscale(image, job.scale, report)
            item.output_name = output_name(item.name, job.scale, item.format)
            path = job.dir / "out" / f"{item.id}.{EXTENSIONS[item.format]}"
            if item.format == "JPEG":
                result.convert("RGB").save(path, "JPEG", quality=95, subsampling=0)
            elif item.format == "WEBP":
                result.save(path, "WEBP", quality=95)
            else:
                result.save(path, "PNG")
            item.output_path = path
            item.progress = 1.0
            item.status = "done"
        except Exception as exc:  # one bad file must not stop the batch
            log.exception("Upscaling %s failed", item.name)
            item.error = str(exc) or exc.__class__.__name__
            item.status = "error"

    def _cleanup_loop(self) -> None:
        while not self._stop.wait(config.CLEANUP_INTERVAL_SECONDS):
            self.cleanup_expired()

    def cleanup_expired(self, now: float | None = None) -> int:
        cutoff = (now or time.time()) - config.JOB_TTL_SECONDS
        with self._lock:
            expired = [j for j in self.jobs.values() if j.created_at < cutoff and j.status == "done"]
            for job in expired:
                del self.jobs[job.id]
        for job in expired:
            shutil.rmtree(job.dir, ignore_errors=True)
        return len(expired)
