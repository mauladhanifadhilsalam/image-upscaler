"""MCP server that lets AI agents upscale local images through the upscaler API.

Run with `python -m agent.mcp_server` (stdio transport). The REST API must be
running; set UPSCALER_API_URL if it is not on http://localhost:8000.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .client import UpscalerClient, UpscalerError, output_path

INSTRUCTIONS = """\
AI image upscaler (Real-ESRGAN). Use `upscale_images` with absolute paths to local
JPG/PNG/WEBP files and scale 2 (200%) or 4 (400%). Results are written next to each
input as <name>_2x.<ext> / <name>_4x.<ext> unless output_dir is given. Call
`upscaler_info` to see the size limits. Large batches on a CPU-only machine can take
minutes; if `upscale_images` returns status "processing", poll `get_job_status` and
then call `download_results`."""


def _absolute(raw: str, what: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise ToolError(f"{what} must be an absolute path, got {raw!r}")
    return path


def create_server(client_factory: Callable[[], UpscalerClient] = UpscalerClient) -> MCPServer:
    server = MCPServer("image-upscaler", instructions=INSTRUCTIONS)

    async def call(fn):
        client = client_factory()
        try:
            return await fn(client)
        except UpscalerError as exc:
            raise ToolError(str(exc)) from exc
        finally:
            await client.aclose()

    @server.tool()
    async def upscale_images(
        paths: list[str],
        ctx: Context,
        scale: Literal[2, 4] = 2,
        output_dir: str | None = None,
        overwrite: bool = False,
        timeout_seconds: int = 600,
    ) -> dict[str, Any]:
        """Upscale one or more local images with AI and save the results to disk.

        Args:
            paths: Absolute paths of JPG, PNG or WEBP images (a batch of up to 20).
            scale: 2 for 200% or 4 for 400%.
            output_dir: Absolute directory for the results. Defaults to each input's own folder.
            overwrite: Replace existing output files instead of failing.
            timeout_seconds: How long to wait for processing before returning the job id
                so you can poll `get_job_status` and call `download_results` later.

        Returns the job id, overall status, and for each input its saved output path and
        dimensions (or the error if that image failed).
        """
        inputs = [_absolute(p, "Each path") for p in paths]
        out_dir = _absolute(output_dir, "output_dir") if output_dir else None

        try:
            targets = [output_path(p, scale, out_dir) for p in inputs]
        except UpscalerError as exc:
            raise ToolError(str(exc)) from exc
        if len(set(targets)) != len(targets):
            raise ToolError("Two inputs would be saved to the same output file; pass a different output_dir")
        if not overwrite:
            existing = [str(t) for t in targets if t.exists()]
            if existing:
                raise ToolError(f"Output already exists: {', '.join(existing)}; pass overwrite=true")

        async def run(client: UpscalerClient) -> dict[str, Any]:
            job = await client.submit([str(p) for p in inputs], scale)
            total = len(job["files"])

            async def progress(state: dict) -> None:
                done = sum(f["status"] in ("done", "error") for f in state["files"])
                await ctx.report_progress(state["progress"] * total, total, f"{done}/{total} images finished")

            job = await client.wait(job["id"], timeout_seconds, progress)
            results = []
            for item, source, target in zip(job["files"], inputs, targets):
                saved = None
                if item["status"] == "done":
                    saved = await client.download_file(job["id"], item, target.parent, overwrite)
                results.append({
                    "input": str(source),
                    "output": str(saved) if saved else None,
                    "status": item["status"],
                    "error": item["error"],
                    "size": f"{item['width']}x{item['height']}",
                    "output_size": f"{item['output_width']}x{item['output_height']}",
                })
            return {"job_id": job["id"], "status": job["status"], "scale": scale, "results": results}

        return await call(run)

    @server.tool()
    async def get_job_status(job_id: str) -> dict[str, Any]:
        """Get the status and progress of an upscaling job started by `upscale_images`."""
        return await call(lambda client: client.status(job_id))

    @server.tool()
    async def download_results(job_id: str, output_dir: str, overwrite: bool = False) -> dict[str, Any]:
        """Save every finished image of a job into `output_dir` (an absolute directory path).

        Use this after `upscale_images` returned before the job finished. Jobs expire an
        hour after they finish.
        """
        target_dir = _absolute(output_dir, "output_dir")

        async def run(client: UpscalerClient) -> dict[str, Any]:
            job = await client.status(job_id)
            saved = [
                str(await client.download_file(job_id, item, target_dir, overwrite))
                for item in job["files"]
                if item["status"] == "done"
            ]
            pending = [f["name"] for f in job["files"] if f["status"] in ("queued", "processing")]
            failed = {f["name"]: f["error"] for f in job["files"] if f["status"] == "error"}
            return {"job_id": job_id, "status": job["status"], "saved": saved, "pending": pending, "failed": failed}

        return await call(run)

    @server.tool()
    async def upscaler_info() -> dict[str, Any]:
        """Report whether the API is up, which upscaler is loaded, and the upload limits."""
        return await call(lambda client: client.info())

    return server


def main() -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)  # don't log every poll request
    create_server().run("stdio")


if __name__ == "__main__":
    main()
