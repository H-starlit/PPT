"""从同目录「视频」文件夹抽取幻灯片，按视频生成同名 PDF。"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import lzma
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable


SOURCE_DIR = Path(__file__).resolve().parent
BASE_DIR = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
            else SOURCE_DIR.parent if SOURCE_DIR.name == "src" else SOURCE_DIR)
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
VIDEO_DIR = BASE_DIR / "视频"  # 输入路径相对于脚本，而非命令行当前目录
OUTPUT_DIR = BASE_DIR / "提取"
CACHE_DIR = BASE_DIR / ".ppt_cache"
LIB_DIR = BUNDLE_DIR / "lib"
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".wmv"}
_verified_bundled_ffmpeg: str | None = None

# 优先使用项目内安装的 Python 依赖，不修改全局 Python 环境。
if (LIB_DIR / "python").is_dir():
    sys.path.insert(0, str(LIB_DIR / "python"))


def save_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def load_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def find_ffmpeg(explicit: str | None) -> str:
    global _verified_bundled_ffmpeg
    if explicit:
        candidate = Path(explicit)
        if candidate.is_file():
            return str(candidate)
        found = shutil.which(explicit)
        if found:
            return found
        raise RuntimeError(f"找不到 FFmpeg：{explicit}")
    binary_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    local_candidates = [LIB_DIR / binary_name, BASE_DIR / binary_name]
    local_candidates.extend(sorted(LIB_DIR.glob(f"*/bin/{binary_name}")))
    for local in local_candidates:
        if local.is_file():
            return str(local)
    compressed = LIB_DIR / "ffmpeg" / "ffmpeg.exe.xz"
    checksum_file = compressed.with_suffix(compressed.suffix + ".sha256")
    if getattr(sys, "frozen", False) and compressed.is_file() and checksum_file.is_file():
        expected_hash = checksum_file.read_text(encoding="ascii").strip().split()[0].lower()
        if len(expected_hash) != 64 or any(c not in "0123456789abcdef" for c in expected_hash):
            raise RuntimeError("内置 FFmpeg 校验信息无效。")
        cache_base = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir())
        cache_dir = cache_base / "视频PPT抽取" / "ffmpeg" / expected_hash[:16]
        cached = cache_dir / "ffmpeg.exe"
        if _verified_bundled_ffmpeg == str(cached) and cached.is_file():
            return str(cached)

        def matches(path: Path) -> bool:
            if not path.is_file():
                return False
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            return digest.hexdigest() == expected_hash

        if matches(cached):
            _verified_bundled_ffmpeg = str(cached)
            return str(cached)
        cache_dir.mkdir(parents=True, exist_ok=True)
        temporary = cache_dir / "ffmpeg.exe.tmp"
        digest = hashlib.sha256()
        try:
            with lzma.open(compressed, "rb") as source, temporary.open("wb") as target:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    target.write(block)
                    digest.update(block)
            if digest.hexdigest() != expected_hash:
                raise RuntimeError("内置 FFmpeg 解压后校验失败。")
            temporary.replace(cached)
        finally:
            temporary.unlink(missing_ok=True)
        _verified_bundled_ffmpeg = str(cached)
        return str(cached)
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise RuntimeError("找不到 FFmpeg。请将 FFmpeg 放在脚本同目录的 lib 文件夹，或将其加入 PATH。")


def extract_frames(video: Path, frame_dir: Path, interval: float, ffmpeg: str, force: bool,
                   progress: Callable[[str], None] | None = None) -> list[Path]:
    metadata_path = frame_dir.parent / "抽帧记录.json"
    source = video.stat()
    identity = {"size": source.st_size, "mtime_ns": source.st_mtime_ns, "interval": interval}
    existing = sorted(frame_dir.glob("*.jpg")) if frame_dir.is_dir() else []
    metadata = load_json(metadata_path)
    if not force and metadata and metadata.get("source") == identity and metadata.get("count") == len(existing) and existing:
        return existing

    frame_dir.mkdir(parents=True, exist_ok=True)
    for frame in frame_dir.glob("*.jpg"):
        frame.unlink()
    metadata_path.unlink(missing_ok=True)
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-i", str(video), "-an", "-vf", f"fps=1/{interval:g}",
        "-q:v", "3", "-start_number", "0", str(frame_dir / "%07d.jpg"),
    ]
    if progress:
        progress("正在抽帧…")
    elif sys.stdout:
        print("  FFmpeg 正在抽帧…", flush=True)
    # A windowed PyInstaller app still gets a console window for console child
    # processes unless CREATE_NO_WINDOW is set explicitly.
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    result = subprocess.run(command, capture_output=True, text=True, errors="replace",
                            creationflags=creationflags)
    if result.returncode != 0:
        message = result.stderr.strip() or f"退出码 {result.returncode}"
        raise RuntimeError(f"FFmpeg 抽帧失败：{message[-1000:]}")
    frames = sorted(frame_dir.glob("*.jpg"))
    if not frames:
        raise RuntimeError("FFmpeg 未生成任何图片，请检查视频是否含有可解码的画面")
    save_json(metadata_path, {"source": identity, "count": len(frames)})
    return frames


def write_pdf(frame_paths: list[Path], destination: Path, interval: float) -> None:
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    temporary = destination.with_suffix(".tmp.pdf")
    pdf = canvas.Canvas(str(temporary), pageCompression=1)
    try:
        for path in frame_paths:
            reader = ImageReader(io.BytesIO(path.read_bytes()))
            width, height = reader.getSize()
            page_width, image_height = width * 0.75, height * 0.75
            footer_height = 34
            pdf.setPageSize((page_width, image_height + footer_height))
            pdf.drawImage(reader, 0, footer_height, width=page_width, height=image_height)
            elapsed = round(int(path.stem) * interval)
            hours, remainder = divmod(elapsed, 3600)
            minutes, seconds = divmod(remainder, 60)
            pdf.setFont("Helvetica-Bold", 16)
            pdf.setFillColorRGB(0.17, 0.22, 0.30)
            pdf.drawRightString(page_width - 16, 10, f"{hours:02d}:{minutes:02d}:{seconds:02d}")
            pdf.showPage()
        pdf.save()
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def process_video(video: Path, interval: float, texture_threshold: float,
                  duplicate_threshold: float, min_stable_frames: int,
                  ffmpeg: str, force: bool, *, output_dir: Path | None = None,
                  work_dir: Path | None = None,
                  progress: Callable[[str], None] | None = None,
                  use_face_detection: bool = True) -> tuple[int, str]:
    work_dir = work_dir or CACHE_DIR / video.name
    output_dir = output_dir or OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    frame_dir = work_dir / "抽取帧"
    pdf_path = output_dir / f"{video.stem}.pdf"
    source = video.stat()
    identity = {"size": source.st_size, "mtime_ns": source.st_mtime_ns, "interval": interval}
    completion_path = work_dir / "完成记录.json"
    completion = load_json(completion_path)
    key = {"source": identity, "texture_threshold": texture_threshold,
           "duplicate_threshold": duplicate_threshold,
           "min_stable_frames": min_stable_frames,
           "use_face_detection": use_face_detection, "algorithm": 7}
    if not force and completion and completion.get("key") == key and pdf_path.is_file() and pdf_path.stat().st_size > 0:
        return int(completion["pages"]), "已跳过（PDF 已存在）"

    frames = extract_frames(video, frame_dir, interval, ffmpeg, force, progress)
    from slide_filter import select_pages as select_slide_pages

    if progress:
        progress("正在筛选与去重…")
    pages = select_slide_pages(frames, work_dir, identity, texture_threshold,
                               duplicate_threshold, min_stable_frames, force,
                               use_face_detection)
    if not pages:
        raise RuntimeError("未找到可用的幻灯片画面")
    if progress:
        progress(f"正在生成 PDF（{len(pages)} 页）…")
    write_pdf(pages, pdf_path, interval)
    save_json(completion_path, {"key": key, "pages": len(pages)})
    return len(pages), str(pdf_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="使用 FFmpeg 从同目录「视频」文件夹抽取画面，每个视频生成一份同名 PDF")
    parser.add_argument("--interval", type=float, default=2.0, help="抽帧间隔（秒，默认 2）")
    parser.add_argument("--texture-threshold", type=float, default=9.0, help="PPT 纹理上限；越低越少实拍画面（默认 9）")
    parser.add_argument("--duplicate-threshold", type=float, default=5.0, help="相似页面合并阈值；越高去重越强（默认 5）")
    parser.add_argument("--min-stable-frames", type=int, default=2, help="连续稳定画面的最少采样帧数（默认 2）")
    parser.add_argument("--ffmpeg", help="FFmpeg 可执行文件路径；默认查找脚本同目录和 PATH")
    parser.add_argument("--force", action="store_true", help="重新处理所有视频")
    parser.add_argument("--list", action="store_true", help="只列出待处理视频")
    args = parser.parse_args()
    if args.interval <= 0 or args.texture_threshold <= 0 or args.duplicate_threshold <= 0 or args.min_stable_frames < 2:
        parser.error("抽帧间隔和阈值必须大于 0，稳定帧数至少为 2")
    if not VIDEO_DIR.is_dir():
        print(f"找不到视频文件夹：{VIDEO_DIR}", file=sys.stderr)
        return 1
    videos = sorted((p for p in VIDEO_DIR.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS), key=lambda p: p.name.casefold())
    if not videos:
        print(f"视频文件夹中没有支持的视频：{VIDEO_DIR}")
        return 1
    stems = [video.stem.casefold() for video in videos]
    if len(stems) != len(set(stems)):
        print("有视频文件主名相同、扩展名不同，无法分别生成同名 PDF；请先重命名其中一个视频。", file=sys.stderr)
        return 1
    if args.list:
        for video in videos:
            print(video.name)
        return 0
    try:
        ffmpeg = find_ffmpeg(args.ffmpeg)
    except RuntimeError as exc:
        print(f"无法开始：{exc}", file=sys.stderr)
        return 1
    try:
        import PIL  # noqa: F401
        import reportlab  # noqa: F401
        import cv2  # noqa: F401
        import numpy  # noqa: F401
    except ImportError as exc:
        print(f"缺少 Python 依赖：{exc}。请运行 python -m pip install -r requirements/runtime.txt。", file=sys.stderr)
        return 1
    OUTPUT_DIR.mkdir(exist_ok=True)
    failed = 0
    for index, video in enumerate(videos, 1):
        print(f"[{index}/{len(videos)}] {video.name}", flush=True)
        try:
            pages, result = process_video(video, args.interval, args.texture_threshold,
                                          args.duplicate_threshold, args.min_stable_frames,
                                          ffmpeg, args.force)
            print(f"  {pages} 页 → {result}", flush=True)
        except Exception as exc:
            failed += 1
            print(f"  失败：{exc}", file=sys.stderr, flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
