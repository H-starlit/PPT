"""Build the GUI app for the current Windows or macOS architecture."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    builddeps = ROOT / ".builddeps"
    packages = ROOT / "lib" / "python"
    if sys.platform == "win32":
        ffmpeg_name = "ffmpeg.exe"
        dist_dir = ROOT / "发布包" / "GUI"
    elif sys.platform == "darwin":
        ffmpeg_name = "ffmpeg"
        dist_dir = ROOT / "发布包" / "macOS"
    else:
        print("GUI 打包目前支持 Windows 和 macOS。", file=sys.stderr)
        return 1
    ffmpeg = next((p for p in (ROOT / "lib").glob(f"*/bin/{ffmpeg_name}") if p.is_file()), None)
    if not builddeps.is_dir() or not packages.is_dir() or ffmpeg is None:
        print("Missing local build tools, Python dependencies, or FFmpeg.", file=sys.stderr)
        return 1
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(builddeps), str(packages), env.get("PYTHONPATH", "")))
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm",
        "--windowed", "--name", "视频PPT抽取",
        "--distpath", str(dist_dir),
        "--workpath", str(ROOT / ".build" / "pyinstaller"),
        "--specpath", str(ROOT / ".build"),
        "--paths", str(packages), "--paths", str(builddeps),
        "--collect-all", "tkinterdnd2",
        "--collect-all", "cv2", "--hidden-import", "cv2",
        "--collect-all", "reportlab",
        "--add-binary", f"{ffmpeg}{os.pathsep}lib/ffmpeg/bin",
        str(ROOT / "src" / "视频PPT抽取_GUI.py"),
    ]
    if sys.platform == "win32":
        command.insert(4, "--onefile")
    else:
        # PyInstaller creates a native .app bundle in onedir mode. A one-file
        # executable is not a native Finder-launchable macOS application.
        command[command.index("--windowed"):command.index("--windowed")] = [
            "--osx-bundle-identifier", "com.hstarl.ppt-extractor"
        ]
    result = subprocess.run(command, cwd=ROOT, env=env)
    if result.returncode:
        return result.returncode
    # The default Windows console code page may not encode the Chinese filename.
    print("GUI executable build completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
