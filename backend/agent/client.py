"""Async client for the upscaler REST API, used by the MCP server."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Awaitable, Callable

import anyio
import httpx
from PIL import Image, UnidentifiedImageError

DEFAULT_API_URL = "http://localhost:8000"
MEDIA_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
EXTENSIONS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}

ProgressFn = Callable[[dict], Awaitable[None]]


class UpscalerError(Exception):
    """A failure worth showing to the agent as-is."""


class UpscalerClient:
    def __init__(self, http: httpx.AsyncClient | None = None, base_url: str | None = None):
        base_url = base_url or os.getenv("UPSCALER_API_URL", DEFAULT_API_URL)
        self.http = http or httpx.AsyncClient(base_url=base_url, timeout=60)

    async def aclose(self) -> None:
        await self.http.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            res = await self.http.request(method, path, **kwargs)
        except httpx.TransportError as exc:
            raise UpscalerError(
                f"Cannot reach the upscaler API at {self.http.base_url} ({exc.__class__.__name__}). "
                "Start it with `cd backend && uvicorn app.main:app --port 8000`, "
                "or set UPSCALER_API_URL."
            ) from exc
        if res.is_error:
            try:
                detail = res.json().get("detail", res.text)
            except ValueError:
                detail = res.text
            raise UpscalerError(f"API error {res.status_code}: {detail}")
        return res

    async def info(self) -> dict:
        health = (await self._request("GET", "/api/health")).json()
        limits = (await self._request("GET", "/api/config")).json()
        return {**health, "limits": limits}

    async def submit(self, paths: list[str], scale: int) -> dict:
        if not paths:
            raise UpscalerError("No image paths given")
        files = []
        for raw in paths:
            path = Path(raw).expanduser()
            fmt = image_format(path)
            files.append(("files", (path.name, path.read_bytes(), MEDIA_TYPES[fmt])))
        res = await self._request("POST", "/api/jobs", data={"scale": str(scale)}, files=files)
        return res.json()

    async def status(self, job_id: str) -> dict:
        return (await self._request("GET", f"/api/jobs/{job_id}")).json()

    async def wait(self, job_id: str, timeout: float, on_progress: ProgressFn | None = None,
                   interval: float = 1.0) -> dict:
        """Poll until every file is finished or `timeout` seconds pass; returns the last status."""
        deadline = time.monotonic() + timeout
        while True:
            job = await self.status(job_id)
            if on_progress:
                await on_progress(job)
            if job["status"] == "done" or time.monotonic() >= deadline:
                return job
            await anyio.sleep(interval)

    async def download_file(self, job_id: str, item: dict, output_dir: Path, overwrite: bool = False) -> Path:
        """Save one finished file as `output_dir/<stem>_<scale>x.<ext>` and return its path."""
        target = output_dir / item["output_name"]
        if target.exists() and not overwrite:
            raise UpscalerError(f"{target} already exists; pass overwrite=true or choose another output_dir")
        res = await self._request("GET", f"/api/jobs/{job_id}/files/{item['id']}")
        output_dir.mkdir(parents=True, exist_ok=True)
        target.write_bytes(res.content)
        return target


def image_format(path: Path) -> str:
    """Return the Pillow format name of a supported image, or raise UpscalerError."""
    if not path.is_file():
        raise UpscalerError(f"File not found: {path}")
    try:
        with Image.open(path) as image:
            fmt = image.format
    except UnidentifiedImageError:
        raise UpscalerError(f"Not an image: {path}")
    if fmt not in MEDIA_TYPES:
        raise UpscalerError(f"{path}: only JPG, PNG and WEBP are supported (got {fmt})")
    return fmt


def output_path(input_path: Path, scale: int, output_dir: Path | None) -> Path:
    """Where the upscaled copy of `input_path` will be saved (mirrors the API's naming)."""
    ext = EXTENSIONS[image_format(input_path)]
    return (output_dir or input_path.parent) / f"{input_path.stem or 'image'}_{scale}x.{ext}"
