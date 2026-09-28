"""将程序和本地依赖制作成可复制到其他 Windows 电脑的便携包。"""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
RUNTIME_REQUIREMENTS = ROOT / "requirements" / "runtime.txt"
DIST = ROOT / "发布包"
PACKAGE = DIST / "视频PPT抽取"


def copy_python_files(source: Path, destination: Path) -> None:
    """只复制运行所需的 Python 文件，排除构建工具和全局依赖。"""
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("python.exe", "python3.dll", "python312.dll",
                 "vcruntime140.dll", "vcruntime140_1.dll", "LICENSE.txt"):
        shutil.copy2(source / name, destination / name)
    shutil.copytree(source / "DLLs", destination / "DLLs",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(source / "Lib", destination / "Lib",
                    ignore=lambda folder, names: {
                        name for name in names
                        if name in {"site-packages", "__pycache__", "ensurepip", "idlelib",
                                    "tkinter", "turtledemo", "venv", "test"}
                        or name.endswith(".pyc")
                    })
    (destination / "python312._pth").write_text(
        "Lib\nDLLs\n..\\python\n..\\..\n.\n", encoding="ascii"
    )


def build(runtime: Path, replace: bool) -> Path:
    if sys.platform != "win32" or sys.version_info[:2] != (3, 12):
        raise RuntimeError("请用 64 位 Python 3.12 在 Windows 上运行打包脚本")
    required = [SOURCE / "extract_ppt_pdf.py", SOURCE / "slide_filter.py", RUNTIME_REQUIREMENTS,
                ROOT / "lib" / "python" / "cv2", ROOT / "lib" / "python" / "PIL",
                ROOT / "lib" / "python" / "numpy", ROOT / "lib" / "python" / "reportlab",
                runtime / "python.exe", runtime / "python312.dll", runtime / "Lib", runtime / "DLLs"]
    ffmpeg = next((path for path in (ROOT / "lib").glob("*/bin/ffmpeg.exe") if path.is_file()), None)
    if ffmpeg is None:
        raise RuntimeError("lib 中没有找到 ffmpeg.exe")
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError("缺少打包文件：" + ", ".join(missing))
    if PACKAGE.exists():
        if not replace:
            raise RuntimeError(f"目标已存在；更新便携包时加 --replace：{PACKAGE}")
        if PACKAGE.resolve().parent != DIST.resolve():
            raise RuntimeError("打包目标不在预期的发布目录中")
        def clear_readonly(function, path, error):
            os.chmod(path, stat.S_IWRITE)
            function(path)

        shutil.rmtree(PACKAGE, onexc=clear_readonly)

    PACKAGE.mkdir(parents=True)
    for name in ("extract_ppt_pdf.py", "slide_filter.py"):
        shutil.copy2(SOURCE / name, PACKAGE / name)
    shutil.copy2(RUNTIME_REQUIREMENTS, PACKAGE / "requirements.txt")
    (PACKAGE / "使用说明.md").write_text(
        "# 视频 PPT 抽取便携版\n\n"
        "1. 把视频文件放入同目录的 `视频` 文件夹。\n"
        "2. 双击 `运行.cmd`。\n"
        "3. 在 `提取` 文件夹查看每个视频对应的同名 PDF。\n\n"
        "本包已包含 Python、FFmpeg、OpenCV 和其他依赖，无需全局安装。"
        "PDF 页面下方带视频时间；已完成的视频再次运行会跳过。"
        "抽帧缓存保存在运行后自动创建的 `.ppt_cache` 文件夹，断电后可继续。\n\n"
        "如需强制重新处理，在命令行运行 `运行.cmd --force`。"
        "可运行 `运行.cmd --help` 查看抽帧间隔和筛选阈值。"
        "请保持本文件夹内的程序、`lib`、`视频`、`提取` 在一起。\n",
        encoding="utf-8"
    )
    (PACKAGE / "视频").mkdir()
    (PACKAGE / "提取").mkdir()
    (PACKAGE / "视频" / "把视频放在这里.txt").write_text(
        "把视频文件放在此文件夹，双击上一级的“运行.cmd”。\n", encoding="utf-8"
    )
    (PACKAGE / "运行.cmd").write_text(
        '@echo off\r\nchcp 65001 >nul\r\ncd /d "%~dp0"\r\n'
        '"lib\\runtime\\python.exe" "extract_ppt_pdf.py" %*\r\n'
        'set "result=%errorlevel%"\r\necho.\r\npause\r\nexit /b %result%\r\n',
        encoding="ascii"
    )
    library = PACKAGE / "lib"
    shutil.copytree(ROOT / "lib" / "python", library / "python",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    copy_python_files(runtime, library / "runtime")
    (library / "ffmpeg" / "bin").mkdir(parents=True)
    shutil.copy2(ffmpeg, library / "ffmpeg" / "bin" / "ffmpeg.exe")
    for name in ("LICENSE", "README.txt"):
        source = ffmpeg.parent.parent / name
        if source.is_file():
            shutil.copy2(source, library / "ffmpeg" / name)

    archive = DIST / "视频PPT抽取_便携版.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        zf.writestr(f"{PACKAGE.name}/提取/", "")
        for path in sorted(PACKAGE.rglob("*")):
            if path.is_file():
                zf.write(path, Path(PACKAGE.name) / path.relative_to(PACKAGE))
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description="制作含 Python、FFmpeg 和依赖的便携版")
    parser.add_argument("--python-runtime", type=Path, default=Path(sys.executable).parent,
                        help="Python 3.12 安装目录；默认使用当前解释器")
    parser.add_argument("--replace", action="store_true", help="替换已有便携包")
    args = parser.parse_args()
    try:
        archive = build(args.python_runtime.resolve(), args.replace)
    except (OSError, RuntimeError) as exc:
        print(f"打包失败：{exc}", file=sys.stderr)
        return 1
    print(f"便携文件夹：{PACKAGE}")
    print(f"压缩包：{archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
