"""Copy the architecture-specific FFmpeg binary from imageio-ffmpeg."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".builddeps"))


def main() -> int:
    if sys.platform != "darwin":
        print("This helper is intended to run on macOS.", file=sys.stderr)
        return 1
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
    except ImportError:
        print("Install requirements/macos-build.txt into .builddeps first.", file=sys.stderr)
        return 1

    source = Path(get_ffmpeg_exe())
    target = ROOT / "lib" / "ffmpeg-imageio" / "bin" / "ffmpeg"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    target.chmod(0o755)
    print(f"Prepared macOS FFmpeg ({source.name}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
