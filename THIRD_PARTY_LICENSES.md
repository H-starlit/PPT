# 第三方许可证

本项目自身代码使用 GNU General Public License v3.0 或更高版本（GPL-3.0-or-later）。本文件列出运行和打包时使用的第三方组件；发布二进制文件时，应同时保留相应组件自带的许可证和版权声明。

| 组件 | 版本/来源 | 许可证 |
|---|---|---|
| FFmpeg（Windows） | gyan.dev Windows essentials 构建 9.0.2 | GPLv3；构建信息和源码地址见 Windows 发布包附带的 `FFmpeg-BUILD-README.txt` |
| FFmpeg（macOS） | imageio-ffmpeg 0.6.0 随附的 Apple Silicon / Intel macOS 二进制 | 发布包附带该二进制的 `ffmpeg -L` 许可证信息和构建来源说明 |
| OpenCV | opencv-python-headless 4.14.0.94 | Apache License 2.0 |
| NumPy | 2.3.5 | BSD 3-Clause 及其随 wheel 附带的组件声明 |
| Pillow | 12.3.0 | Pillow 自带许可证 |
| ReportLab | 4.4.9 | BSD |
| tkinterdnd2 | 0.6.3 | MIT |
| imageio-ffmpeg | 0.6.0（仅用于 macOS 构建时取得 FFmpeg） | BSD 2-Clause |
| PyInstaller | 6.22.3（仅构建工具） | GPL with bootloader exception |

许可证文本和版权声明以各组件发行包内的文件为准。FFmpeg 的许可证条件尤其重要：当前内置构建包含 GPL 部件，因此本项目发布包按 GPLv3 发行。项目不包含用户的视频、PDF 或抽帧缓存。
