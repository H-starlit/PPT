"""生成带拖放界面的单文件 Windows EXE。"""

from __future__ import annotations

import os
import hashlib
import lzma
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    builddeps = ROOT / ".builddeps"
    packages = ROOT / "lib" / "python"
    ffmpeg = next((p for p in (ROOT / "lib").glob("*/bin/ffmpeg.exe") if p.is_file()), None)
    if not builddeps.is_dir() or not packages.is_dir() or ffmpeg is None:
        print("缺少本地打包工具、Python 依赖或 FFmpeg。", file=sys.stderr)
        return 1
    compressed_dir = ROOT / ".build" / "ffmpeg"
    compressed_dir.mkdir(parents=True, exist_ok=True)
    compressed_ffmpeg = compressed_dir / "ffmpeg.exe.xz"
    checksum_file = compressed_dir / "ffmpeg.exe.xz.sha256"
    digest = hashlib.sha256()
    with ffmpeg.open("rb") as source, lzma.open(compressed_ffmpeg, "wb", preset=9) as target:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            target.write(block)
            digest.update(block)
    checksum_file.write_text(digest.hexdigest() + "\n", encoding="ascii")
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(builddeps), str(packages), env.get("PYTHONPATH", "")))
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm",
        "--onefile", "--windowed", "--name", "视频PPT抽取",
        "--distpath", str(ROOT / "发布包" / "GUI"),
        "--workpath", str(ROOT / ".build" / "pyinstaller"),
        "--specpath", str(ROOT / ".build"),
        "--paths", str(packages), "--paths", str(builddeps),
        "--collect-all", "tkinterdnd2",
        "--collect-all", "cv2", "--hidden-import", "cv2",
        "--collect-all", "reportlab",
        "--add-data", f"{compressed_ffmpeg}{os.pathsep}lib/ffmpeg",
        "--add-data", f"{checksum_file}{os.pathsep}lib/ffmpeg",
        str(ROOT / "src" / "视频PPT抽取_GUI.py"),
    ]
    result = subprocess.run(command, cwd=ROOT, env=env)
    if result.returncode:
        return result.returncode
    # The default Windows console code page may not encode the Chinese filename.
    print("GUI executable build completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
