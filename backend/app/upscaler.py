"""Image upscaling backends.

`RealESRGANUpscaler` runs the Real-ESRGAN models; `ResizeUpscaler` is a
Lanczos fallback used in tests and when no model weights are present.
"""

from __future__ import annotations

import logging
import math
import threading
from typing import Callable, Protocol

from PIL import Image

from . import config

log = logging.getLogger(__name__)

ProgressFn = Callable[[float], None]


class Upscaler(Protocol):
    name: str

    def upscale(self, image: Image.Image, scale: int, progress: ProgressFn | None = None) -> Image.Image: ...


def _split_alpha(image: Image.Image) -> tuple[Image.Image, Image.Image | None]:
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        return rgba.convert("RGB"), rgba.getchannel("A")
    return image.convert("RGB"), None


class ResizeUpscaler:
    name = "lanczos"

    def upscale(self, image: Image.Image, scale: int, progress: ProgressFn | None = None) -> Image.Image:
        out = image.resize((image.width * scale, image.height * scale), Image.LANCZOS)
        if progress:
            progress(1.0)
        return out


class RealESRGANUpscaler:
    name = "real-esrgan"

    def __init__(self, models_dir=config.MODELS_DIR, tile=config.TILE_SIZE, overlap=config.TILE_OVERLAP):
        import torch
        from spandrel import ImageModelDescriptor, ModelLoader

        self._torch = torch
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.half = self.device.type == "cuda"
        self.tile = tile
        self.overlap = overlap
        self._lock = threading.Lock()
        self.models = {}
        for scale, filename in config.MODEL_FILES.items():
            path = models_dir / filename
            model = ModelLoader(device=self.device).load_from_file(path)
            if not isinstance(model, ImageModelDescriptor) or model.scale != scale:
                raise ValueError(f"{filename} is not a {scale}x image model")
            model.eval()
            if self.half and model.supports_half:
                model.half()
            self.models[scale] = model
        log.info("Loaded Real-ESRGAN models %s on %s", sorted(self.models), self.device)

    def upscale(self, image: Image.Image, scale: int, progress: ProgressFn | None = None) -> Image.Image:
        rgb, alpha = _split_alpha(image)
        with self._lock:
            out = self._run(rgb, self.models[scale], scale, progress)
        if alpha is not None:
            out.putalpha(alpha.resize(out.size, Image.LANCZOS))
        return out

    def _run(self, rgb: Image.Image, model, scale: int, progress: ProgressFn | None) -> Image.Image:
        torch = self._torch
        dtype = torch.float16 if self.half and model.supports_half else torch.float32
        tensor = torch.frombuffer(bytearray(rgb.tobytes()), dtype=torch.uint8)
        tensor = tensor.view(rgb.height, rgb.width, 3).permute(2, 0, 1).unsqueeze(0)
        tensor = tensor.to(self.device, dtype=dtype) / 255.0

        _, _, h, w = tensor.shape
        output = torch.empty((1, 3, h * scale, w * scale), dtype=dtype, device=self.device)
        tiles_y, tiles_x = math.ceil(h / self.tile), math.ceil(w / self.tile)
        total, done = tiles_x * tiles_y, 0

        with torch.inference_mode():
            for ty in range(tiles_y):
                for tx in range(tiles_x):
                    # Tile bounds, then the same tile padded by the overlap on each side.
                    y0, x0 = ty * self.tile, tx * self.tile
                    y1, x1 = min(y0 + self.tile, h), min(x0 + self.tile, w)
                    py0, px0 = max(y0 - self.overlap, 0), max(x0 - self.overlap, 0)
                    py1, px1 = min(y1 + self.overlap, h), min(x1 + self.overlap, w)

                    result = model(tensor[:, :, py0:py1, px0:px1])

                    # Keep only the unpadded centre of the upscaled tile.
                    oy, ox = (y0 - py0) * scale, (x0 - px0) * scale
                    output[:, :, y0 * scale : y1 * scale, x0 * scale : x1 * scale] = result[
                        :, :, oy : oy + (y1 - y0) * scale, ox : ox + (x1 - x0) * scale
                    ]
                    done += 1
                    if progress:
                        progress(done / total)

        array = (output.squeeze(0).clamp(0, 1) * 255.0).round().to(torch.uint8).permute(1, 2, 0).cpu().numpy()
        return Image.fromarray(array, "RGB")


def load_upscaler() -> Upscaler:
    missing = [f for f in config.MODEL_FILES.values() if not (config.MODELS_DIR / f).exists()]
    if missing:
        log.warning("Model weights missing (%s); falling back to Lanczos resize. "
                    "Run scripts/download_models.py.", ", ".join(missing))
        return ResizeUpscaler()
    return RealESRGANUpscaler()
