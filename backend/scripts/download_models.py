"""Download the Real-ESRGAN weights used for 2x and 4x upscaling."""

import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402

URLS = {
    "RealESRGAN_x2plus.pth": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth",
    "RealESRGAN_x4plus.pth": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
}


def main() -> None:
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for filename in config.MODEL_FILES.values():
        target = config.MODELS_DIR / filename
        if target.exists():
            print(f"{filename} already present")
            continue
        print(f"Downloading {filename}...")
        partial = target.with_suffix(".part")
        urllib.request.urlretrieve(URLS[filename], partial)
        partial.rename(target)
    print(f"Models are in {config.MODELS_DIR}")


if __name__ == "__main__":
    main()
