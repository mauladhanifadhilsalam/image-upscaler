import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

MODELS_DIR = Path(os.getenv("MODELS_DIR", BASE_DIR / "models"))
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", BASE_DIR / "storage"))
# Built web UI (`npm run build`); served at / when present.
FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST", BASE_DIR.parent / "frontend" / "dist"))

MODEL_FILES = {
    2: "RealESRGAN_x2plus.pth",
    4: "RealESRGAN_x4plus.pth",
}
SUPPORTED_SCALES = tuple(MODEL_FILES)

MAX_FILE_BYTES = int(os.getenv("MAX_FILE_MB", "10")) * 1024 * 1024
MAX_FILES_PER_JOB = int(os.getenv("MAX_FILES_PER_JOB", "20"))
# Longest side of the input image allowed for each scale; keeps outputs around 8K.
MAX_INPUT_SIDE = {
    2: int(os.getenv("MAX_INPUT_SIDE_2X", "4096")),
    4: int(os.getenv("MAX_INPUT_SIDE_4X", "2048")),
}

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}

# Tiled inference keeps memory bounded on large images.
TILE_SIZE = int(os.getenv("TILE_SIZE", "512"))
TILE_OVERLAP = int(os.getenv("TILE_OVERLAP", "32"))

JOB_TTL_SECONDS = int(os.getenv("JOB_TTL_SECONDS", "3600"))
CLEANUP_INTERVAL_SECONDS = int(os.getenv("CLEANUP_INTERVAL_SECONDS", "300"))

CORS_ORIGINS = [o for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o]
