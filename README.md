# 纯AI生成，只适合希望图方便直接拿来用的人，避免重复造轮子，但是代码质量嘛，，，只能说没什么参考价值

# 视频 PPT 抽取

本项目按 GNU General Public License v3.0 或更高版本（GPL-3.0-or-later）发布，详见 [LICENSE](LICENSE)。第三方组件及其许可证见 [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)。

把视频放在本程序同目录的 `视频` 文件夹中，运行后会在同目录的 `提取` 文件夹得到**每个视频一份同名 PDF**，例如 `视频/课程01.mp4` 对应 `提取/课程01.pdf`。输入路径由脚本位置确定，从其他工作目录运行也一样。视频抽帧由 FFmpeg 完成，Python 负责画面去重和生成 PDF。

## 单文件图形版

Windows 版双击 `发布包/GUI/视频PPT抽取.exe`；macOS 版从 GitHub Release 下载与芯片匹配的 ZIP（Apple Silicon 选 `arm64`，Intel 选 `x86_64`），解压后可将 `视频PPT抽取.app` 拖到“应用程序”。把多个视频拖入窗口，或点击“添加视频”。确认输出文件夹和识别设置后点击“开始提取”；程序会逐个生成与视频同名的 PDF，并显示处理进度和估算的剩余分钟数。可以关闭“启用人脸识别”以跳过人脸检测；这会加快筛选，但也可能让包含人物的画面进入 PDF。拖入的视频可以来自不同文件夹，但同一批次不能有重名的视频文件。窗口启动尺寸会根据屏幕空间自动选择；调整窗口大小时，识别参数会重新排列，视频列表可滚动查看较长路径。

Windows 默认把结果放在 exe 同目录的 `提取` 文件夹。macOS 默认放在 `~/Documents/视频PPT抽取/提取`，避免向 `/Applications` 应用程序目录写入文件；也可以在窗口内另选位置。Windows 会适配高 DPI 缩放，macOS 使用系统原生 Tk 界面缩放。macOS 应用目前未做 Apple Developer ID 签名和公证；首次打开若出现安全提示，请在 Finder 中右键应用并选择“打开”。

Windows exe 和 macOS app 均包含 Python、FFmpeg 和所需依赖，无需另外安装 Python、FFmpeg 或 Homebrew。抽帧缓存放在输出文件夹的上一级 `.ppt_cache` 中，便于断电后复用；再次处理同一视频和输出位置时会跳过已完成的 PDF。

## 便携版：双击运行

打开 `发布包/视频PPT抽取_便携版.zip`，解压后把视频放入其中的 `视频` 文件夹，双击 `运行.cmd`。同名 PDF 会出现在 `提取` 文件夹。便携包自带 64 位 Python 3.12、FFmpeg 和所需依赖，复制到其他 64 位 Windows 电脑后无需安装 Python 或配置环境变量。请保持压缩包内的文件夹结构，不要单独移动 `运行.cmd`。

便携包只包含程序和依赖，不包含本工作目录中的原始视频、PDF 和抽帧缓存。再次运行会跳过已完成的视频；需要重做时，可在命令行执行 `运行.cmd --force`。

## 源码运行

项目源码位于 `src/`，构建脚本位于 `scripts/`，依赖清单位于 `requirements/`。当前程序使用 **64 位 Python 3.12**。如需源码运行，可把依赖安装到项目本地目录，不修改全局 Python 环境：

```powershell
python -m pip install --target lib/python -r requirements/runtime.txt
python src/extract_ppt_pdf.py
```

如当前终端没有 `python` 命令，可直接使用便携版的 `运行.cmd`。

支持 MP4、MOV、MKV、AVI、M4V、WMV。默认每 2 秒取样一次，优先保留连续稳定、版式较像 PPT 且未检测到人脸的画面；同一页逐步出现文字或图线时只保留最后一帧。每页下方标注相应的视频时间。完成的视频再次运行时会跳过。抽取图片与筛选记录保存在 `.ppt_cache`，中断后可继续；`提取` 文件夹只存放最终 PDF。若视频只有实拍而没有正文 PPT，会保留无人物的片头标题页。

```powershell
python src/extract_ppt_pdf.py --list
python src/extract_ppt_pdf.py --interval 1 --texture-threshold 10 --duplicate-threshold 6
python src/extract_ppt_pdf.py --min-stable-frames 3
python src/extract_ppt_pdf.py --ffmpeg "D:\工具\ffmpeg\bin\ffmpeg.exe"
python src/extract_ppt_pdf.py --force
```

FFmpeg 来源：[FFmpeg 官方下载页](https://ffmpeg.org/download.html)列出的 [gyan.dev Windows release essentials 构建](https://www.gyan.dev/ffmpeg/builds/)。如自行更换版本，将其 `bin/ffmpeg.exe` 放在 `lib` 的一级子文件夹中即可。

## GitHub Releases

Windows 和 macOS 程序通过 GitHub Releases 分发；GitHub Packages 面向 npm、NuGet、Maven、Gradle、RubyGems 和容器等包格式，不适合直接托管本项目的桌面安装包。向仓库推送 `v` 开头的版本标签（例如 `v1.0.0`）后，GitHub Actions 会分别在 Windows、Apple Silicon Mac 和 Intel Mac 上安装依赖并构建，再将 Windows exe 与两种架构的 macOS app ZIP 上传到同一 Release。Release 附带 SHA-256 校验文件和许可证资料。

```powershell
git tag v1.0.0
git push origin v1.0.0
```

## 重新打包

在源码目录使用 64 位 Python 3.12 运行 `python scripts/打包便携版.py --replace`，即可更新 `发布包` 中的便携文件夹和 ZIP。打包脚本使用当前 Python 安装目录中的标准库，排除其全局安装的软件包；视频、提取结果和缓存不会进入压缩包。

图形版使用 `python scripts/打包GUI.py` 按当前系统生成桌面程序：Windows 生成单文件 exe，macOS 生成 `.app` 应用包。在 macOS 本机打包前，需要 Python 3.12、Tk 支持和 Homebrew：

```bash
brew install python@3.12 python-tk@3.12
python3.12 -m pip install --target .builddeps -r requirements/build.txt -r requirements/macos-build.txt
python3.12 -m pip install --target lib/python -r requirements/release.txt
python3.12 scripts/准备macOS_FFmpeg.py
python3.12 scripts/打包GUI.py
```

Windows 和 macOS 的依赖分别在 `requirements/build.txt`、`requirements/macos-build.txt` 和 `requirements/release.txt` 中管理。GitHub Release 工作流会在各自平台准备 FFmpeg 和依赖；这些依赖目录不会提交到仓库。

页数偏少时，可缩短 `--interval`，或提高 `--texture-threshold`；重复页偏多时，可提高 `--duplicate-threshold` 或 `--min-stable-frames`。默认值分别为 2 秒、9、5 和 2 帧。`--force` 会重新抽帧并处理所有视频；仅调整筛选参数时会复用缓存帧。人脸与版式识别是启发式判断，可能漏掉短暂出现的 PPT，也不能保证排除所有实拍画面。此程序提取的是视频画面，不能恢复可编辑的原始 PPT 元素。
