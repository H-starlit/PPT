"""拖入多个视频，逐个提取 PPT 并导出同名 PDF。"""

from __future__ import annotations

import hashlib
import os
import queue
import sys
import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".builddeps"))

from tkinterdnd2 import DND_FILES, TkinterDnD

import extract_ppt_pdf as core


VIDEO_TYPES = [("视频文件", "*.mp4 *.mov *.mkv *.avi *.m4v *.wmv"), ("所有文件", "*.*")]
DEFAULT_SETTINGS = {"interval": "2", "texture": "9", "duplicate": "5", "stable": "2"}


def cache_for(video: Path, output_dir: Path) -> Path:
    digest = hashlib.sha256(str(video.resolve()).casefold().encode("utf-8")).hexdigest()[:16]
    return output_dir.parent / ".ppt_cache" / "GUI" / digest


def extract_one(video: Path, output_dir: Path, settings: dict, progress=None) -> tuple[int, str]:
    ffmpeg = core.find_ffmpeg(None)
    return core.process_video(video, settings["interval"], settings["texture"],
                              settings["duplicate"], settings["stable"], ffmpeg, False,
                              output_dir=output_dir,
                              work_dir=cache_for(video, output_dir), progress=progress)


class ExtractorApp:
    def __init__(self) -> None:
        self.root = TkinterDnD.Tk()
        self.root.title("视频 PPT 抽取")
        self.root.geometry("900x610")
        self.root.minsize(680, 460)
        self.root.configure(bg="#f4f6f9")
        self.paths: list[Path] = []
        self.rows: dict[Path, str] = {}
        self.events: queue.Queue[tuple] = queue.Queue()
        self.running = False
        self.output = tk.StringVar(value=str(core.OUTPUT_DIR))
        self.interval = tk.StringVar(value=DEFAULT_SETTINGS["interval"])
        self.texture = tk.StringVar(value=DEFAULT_SETTINGS["texture"])
        self.duplicate = tk.StringVar(value=DEFAULT_SETTINGS["duplicate"])
        self.stable = tk.StringVar(value=DEFAULT_SETTINGS["stable"])
        self.summary = tk.StringVar(value="拖入视频，或点击“添加视频”")
        self._build()
        self.root.after(100, self._poll)

    def _build(self) -> None:
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Treeview", rowheight=28, font=("Microsoft YaHei UI", 10))
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"))

        outer = tk.Frame(self.root, bg="#f4f6f9", padx=22, pady=18)
        outer.pack(fill="both", expand=True)
        tk.Label(outer, text="视频 PPT 抽取", bg="#f4f6f9", fg="#1b304b",
                 font=("Microsoft YaHei UI", 20, "bold")).pack(anchor="w")
        tk.Label(outer, text="拖入多个视频，自动筛选 PPT 画面并为每个视频生成同名 PDF",
                 bg="#f4f6f9", fg="#52657b", font=("Microsoft YaHei UI", 10)).pack(anchor="w", pady=(4, 15))

        buttons = tk.Frame(outer, bg="#f4f6f9")
        buttons.pack(fill="x", pady=(0, 10))
        self.add_button = ttk.Button(buttons, text="添加视频", command=self._choose_files)
        self.add_button.pack(side="left")
        self.remove_button = ttk.Button(buttons, text="移除选中", command=self._remove_selected)
        self.remove_button.pack(side="left", padx=8)
        self.clear_button = ttk.Button(buttons, text="清空列表", command=self._clear)
        self.clear_button.pack(side="left")

        drop = tk.Frame(outer, bg="#e9f2fb", highlightbackground="#94bce8", highlightthickness=1)
        drop.pack(fill="x", pady=(0, 12))
        drop_label = tk.Label(drop, text="将视频文件拖到这里，也可以拖到下方列表",
                              bg="#e9f2fb", fg="#255486", font=("Microsoft YaHei UI", 11),
                              pady=14)
        drop_label.pack(fill="x")
        for target in (drop, drop_label):
            target.drop_target_register(DND_FILES)
            target.dnd_bind("<<Drop>>", self._drop)

        columns = ("name", "folder", "status")
        self.table = ttk.Treeview(outer, columns=columns, show="headings", selectmode="extended")
        self.table.heading("name", text="视频文件")
        self.table.heading("folder", text="所在文件夹")
        self.table.heading("status", text="状态")
        self.table.column("name", width=220, minwidth=150)
        self.table.column("folder", width=390, minwidth=180)
        self.table.column("status", width=170, minwidth=110)
        self.table.pack(fill="both", expand=True)
        self.table.drop_target_register(DND_FILES)
        self.table.dnd_bind("<<Drop>>", self._drop)

        output_row = tk.Frame(outer, bg="#f4f6f9")
        output_row.pack(fill="x", pady=(14, 5))
        tk.Label(output_row, text="输出文件夹", bg="#f4f6f9", fg="#1b304b",
                 font=("Microsoft YaHei UI", 10)).pack(side="left")
        self.output_entry = ttk.Entry(output_row, textvariable=self.output)
        self.output_entry.pack(side="left", fill="x", expand=True, padx=10)
        self.folder_button = ttk.Button(output_row, text="选择", command=self._choose_output)
        self.folder_button.pack(side="left")

        settings = ttk.LabelFrame(outer, text="识别参数（默认值适合当前视频）", padding=(10, 6))
        settings.pack(fill="x", pady=(6, 0))
        fields = [
            ("抽帧间隔（秒）", self.interval, "越小越容易保留短页面"),
            ("PPT 纹理阈值", self.texture, "越大越容易保留实拍画面"),
            ("重复合并阈值", self.duplicate, "越大去重越强"),
            ("最少稳定帧数", self.stable, "越大越少保留短暂画面"),
        ]
        for column, (label, variable, tip) in enumerate(fields):
            cell = tk.Frame(settings, bg="#f4f6f9")
            cell.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 8, 8))
            tk.Label(cell, text=label, bg="#f4f6f9", fg="#1b304b",
                     font=("Microsoft YaHei UI", 9)).pack(anchor="w")
            entry = ttk.Entry(cell, textvariable=variable, width=8)
            entry.pack(anchor="w", pady=(3, 0))
            tk.Label(cell, text=tip, bg="#f4f6f9", fg="#718096",
                     font=("Microsoft YaHei UI", 8)).pack(anchor="w")
            settings.columnconfigure(column, weight=1)
        ttk.Button(settings, text="恢复默认值", command=self._reset_settings).grid(
            row=0, column=len(fields), rowspan=2, padx=(2, 0), sticky="e")
        self.setting_entries = [child for child in settings.winfo_children()]

        bottom = tk.Frame(outer, bg="#f4f6f9")
        bottom.pack(fill="x", pady=(13, 0))
        self.start_button = ttk.Button(bottom, text="开始提取", command=self._start)
        self.start_button.pack(side="left")
        ttk.Button(bottom, text="打开输出文件夹", command=self._open_output).pack(side="left", padx=9)
        self.spinner = ttk.Progressbar(bottom, mode="indeterminate", length=130)
        self.spinner.pack(side="left", padx=12)
        tk.Label(bottom, textvariable=self.summary, bg="#f4f6f9", fg="#52657b",
                 font=("Microsoft YaHei UI", 9)).pack(side="right")

    def _reset_settings(self) -> None:
        self.interval.set(DEFAULT_SETTINGS["interval"])
        self.texture.set(DEFAULT_SETTINGS["texture"])
        self.duplicate.set(DEFAULT_SETTINGS["duplicate"])
        self.stable.set(DEFAULT_SETTINGS["stable"])

    def _add_paths(self, paths: list[str]) -> None:
        if self.running:
            return
        rejected = []
        for raw in paths:
            path = Path(raw).resolve()
            if not path.is_file() or path.suffix.lower() not in core.VIDEO_EXTENSIONS:
                rejected.append(path.name)
                continue
            if path in self.rows:
                continue
            self.paths.append(path)
            self.rows[path] = self.table.insert("", "end", values=(path.name, str(path.parent), "待处理"))
        self.summary.set(f"已添加 {len(self.paths)} 个视频")
        if rejected:
            messagebox.showwarning("无法添加", "以下文件不是支持的视频格式：\n" + "\n".join(rejected[:10]))

    def _drop(self, event) -> None:
        self._add_paths(list(self.root.tk.splitlist(event.data)))

    def _choose_files(self) -> None:
        chosen = filedialog.askopenfilenames(parent=self.root, title="选择视频文件", filetypes=VIDEO_TYPES)
        self._add_paths(list(chosen))

    def _remove_selected(self) -> None:
        if self.running:
            return
        selected = set(self.table.selection())
        for path in list(self.paths):
            if self.rows[path] in selected:
                self.table.delete(self.rows.pop(path))
                self.paths.remove(path)
        self.summary.set(f"已添加 {len(self.paths)} 个视频")

    def _clear(self) -> None:
        if self.running:
            return
        for row in self.table.get_children():
            self.table.delete(row)
        self.paths.clear()
        self.rows.clear()
        self.summary.set("拖入视频，或点击“添加视频”")

    def _choose_output(self) -> None:
        chosen = filedialog.askdirectory(parent=self.root, title="选择 PDF 输出文件夹")
        if chosen:
            self.output.set(chosen)

    def _open_output(self) -> None:
        folder = Path(self.output.get().strip()).expanduser()
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)

    def _set_running(self, value: bool) -> None:
        self.running = value
        state = "disabled" if value else "normal"
        for widget in (self.add_button, self.remove_button, self.clear_button,
                       self.folder_button, self.output_entry, self.start_button):
            widget.configure(state=state)
        for cell in self.setting_entries:
            for widget in cell.winfo_children():
                if isinstance(widget, ttk.Entry):
                    widget.configure(state=state)
        if value:
            self.spinner.start(12)
        else:
            self.spinner.stop()

    def _start(self) -> None:
        if not self.paths:
            messagebox.showinfo("请添加视频", "先拖入视频文件，或点击“添加视频”。")
            return
        try:
            settings = {
                "interval": float(self.interval.get()),
                "texture": float(self.texture.get()),
                "duplicate": float(self.duplicate.get()),
                "stable": int(self.stable.get()),
            }
            if settings["interval"] <= 0 or settings["texture"] <= 0 or settings["duplicate"] <= 0 or settings["stable"] < 2:
                raise ValueError
        except ValueError:
            messagebox.showerror("参数无效", "请填写有效参数：前三项必须大于 0，最少稳定帧数至少为 2。")
            return
        stems = [path.stem.casefold() for path in self.paths]
        if len(stems) != len(set(stems)):
            messagebox.showerror("文件名重复", "列表中有不同视频使用相同文件名。请移除或重命名其中一个，以免 PDF 相互覆盖。")
            return
        output_dir = Path(self.output.get().strip()).expanduser().resolve()
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("无法创建输出文件夹", str(exc))
            return
        self._set_running(True)
        self.summary.set(f"正在处理 1/{len(self.paths)}")
        threading.Thread(target=self._worker, args=(list(self.paths), output_dir, settings), daemon=True).start()

    def _worker(self, paths: list[Path], output_dir: Path, settings: dict) -> None:
        ok = 0
        for index, path in enumerate(paths, 1):
            self.events.put(("summary", f"正在处理 {index}/{len(paths)}"))
            self.events.put(("status", path, "处理中"))
            try:
                pages, result = extract_one(
                    path, output_dir, settings,
                    progress=lambda message, p=path: self.events.put(("status", p, message)))
                status = f"完成 · {pages} 页" if "已跳过" not in result else f"已有 PDF · {pages} 页"
                self.events.put(("status", path, status))
                ok += 1
            except Exception as exc:
                self.events.put(("status", path, "失败"))
                self.events.put(("error", f"{path.name}：{exc}"))
        self.events.put(("done", ok, len(paths)))

    def _poll(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "status":
                    _, path, value = event
                    if path in self.rows:
                        self.table.set(self.rows[path], "status", value)
                elif event[0] == "summary":
                    self.summary.set(event[1])
                elif event[0] == "error":
                    messagebox.showerror("提取失败", event[1])
                elif event[0] == "done":
                    self._set_running(False)
                    self.summary.set(f"完成 {event[1]}/{event[2]} 个视频")
                    if event[1] == event[2]:
                        messagebox.showinfo("提取完成", f"已处理 {event[1]} 个视频。\nPDF 保存在：\n{self.output.get()}")
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    if len(sys.argv) == 4 and sys.argv[1] == "--self-test":
        video, output = Path(sys.argv[2]), Path(sys.argv[3])
        try:
            extract_one(video, output, {"interval": 2.0, "texture": 9.0,
                                        "duplicate": 5.0, "stable": 2})
            return 0
        except Exception:
            output.mkdir(parents=True, exist_ok=True)
            (output / "selftest_error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            return 1
    app = ExtractorApp()
    if len(sys.argv) == 2 and sys.argv[1] == "--smoke-gui":
        app.root.after(1500, app.root.destroy)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
