"""拖入多个视频，逐个提取 PPT 并导出同名 PDF。"""

from __future__ import annotations

import hashlib
import os
import queue
import sys
import threading
import time
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".builddeps"))

from tkinterdnd2 import DND_FILES, TkinterDnD

import extract_ppt_pdf as core


VIDEO_TYPES = [("视频文件", "*.mp4 *.mov *.mkv *.avi *.m4v *.wmv"), ("所有文件", "*.*")]
DEFAULT_SETTINGS = {"interval": "2", "texture": "9", "duplicate": "5", "stable": "2",
                    "face_detection": True}


def cache_for(video: Path, output_dir: Path) -> Path:
    digest = hashlib.sha256(str(video.resolve()).casefold().encode("utf-8")).hexdigest()[:16]
    return output_dir.parent / ".ppt_cache" / "GUI" / digest


def extract_one(video: Path, output_dir: Path, settings: dict, progress=None) -> tuple[int, str]:
    ffmpeg = core.find_ffmpeg(None)
    return core.process_video(video, settings["interval"], settings["texture"],
                              settings["duplicate"], settings["stable"], ffmpeg, False,
                              output_dir=output_dir,
                              work_dir=cache_for(video, output_dir), progress=progress,
                              use_face_detection=settings["face_detection"])


class ExtractorApp:
    def __init__(self) -> None:
        self.root = TkinterDnD.Tk()
        self.root.title("视频 PPT 抽取")
        self._size_for_screen()
        self.root.configure(bg="#f3f6fa")
        self.paths: list[Path] = []
        self.rows: dict[Path, str] = {}
        self.events: queue.Queue[tuple] = queue.Queue()
        self.running = False
        self.output = tk.StringVar(value=str(core.OUTPUT_DIR))
        self.interval = tk.StringVar(value=DEFAULT_SETTINGS["interval"])
        self.texture = tk.StringVar(value=DEFAULT_SETTINGS["texture"])
        self.duplicate = tk.StringVar(value=DEFAULT_SETTINGS["duplicate"])
        self.stable = tk.StringVar(value=DEFAULT_SETTINGS["stable"])
        self.face_detection = tk.BooleanVar(value=DEFAULT_SETTINGS["face_detection"])
        self.summary = tk.StringVar(value="拖入视频，或点击“添加视频”")
        self.eta = tk.StringVar(value="")
        self.progress_value = tk.DoubleVar(value=0)
        self.setting_cells: list[tk.Frame] = []
        self._settings_layout_after: str | None = None
        self._build()
        self.root.after_idle(self._layout_settings)
        self.root.after(100, self._poll)

    def _size_for_screen(self) -> None:
        """Choose a comfortable initial size while leaving room for taskbars."""
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        min_width = min(620, max(420, screen_width - 32))
        min_height = min(500, max(360, screen_height - 96))
        width = min(screen_width - 32, 1040, max(min_width, int(screen_width * .82)))
        height = min(screen_height - 64, 760, max(min_height, int(screen_height * .86)))
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.minsize(min_width, min_height)

        # Tk fonts use points while its geometry uses pixels. Sync them to the
        # monitor DPI so Windows scaling keeps text crisp and controls readable.
        try:
            dpi = self.root.winfo_fpixels("1i")
            self.root.tk.call("tk", "scaling", dpi / 72.0)
        except (tk.TclError, ZeroDivisionError):
            pass

    def _build(self) -> None:
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("TButton", padding=(11, 6), font=(self.font_family, 9))
        style.configure("TEntry", padding=(6, 5), font=(self.font_family, 9))
        style.configure("Treeview", rowheight=29, font=(self.font_family, 9),
                        background="#ffffff", fieldbackground="#ffffff", foreground="#25364a")
        style.configure("Treeview.Heading", font=(self.font_family, 9, "bold"),
                        background="#edf2f8", foreground="#43566d", padding=(8, 7))
        style.configure("Horizontal.TProgressbar", troughcolor="#e3eaf2", background="#3978c5",
                        bordercolor="#e3eaf2", lightcolor="#3978c5", darkcolor="#3978c5")

        outer = tk.Frame(self.root, bg="#f3f6fa", padx=20, pady=15)
        outer.pack(fill="both", expand=True)
        tk.Label(outer, text="视频 PPT 抽取", bg="#f3f6fa", fg="#1b304b",
                 font=(self.font_family, 21, "bold")).pack(anchor="w")
        tk.Label(outer, text="导入视频，自动筛选画面并分别生成 PDF",
                 bg="#f3f6fa", fg="#65758a", font=(self.font_family, 10)).pack(anchor="w", pady=(3, 12))

        buttons = tk.Frame(outer, bg="#f3f6fa")
        buttons.pack(fill="x", pady=(0, 10))
        self.add_button = ttk.Button(buttons, text="添加视频", command=self._choose_files)
        self.add_button.pack(side="left")
        self.remove_button = ttk.Button(buttons, text="移除选中", command=self._remove_selected)
        self.remove_button.pack(side="left", padx=8)
        self.clear_button = ttk.Button(buttons, text="清空列表", command=self._clear)
        self.clear_button.pack(side="left")

        drop = tk.Frame(outer, bg="#eaf2fc", highlightbackground="#c4d8f1", highlightthickness=1)
        drop.pack(fill="x", pady=(0, 10))
        drop_label = tk.Label(drop, text="将视频拖到这里，或拖入下方列表",
                              bg="#eaf2fc", fg="#315d91", font=(self.font_family, 10),
                              pady=12)
        drop_label.pack(fill="x")
        for target in (drop, drop_label):
            target.drop_target_register(DND_FILES)
            target.dnd_bind("<<Drop>>", self._drop)

        table_wrap = tk.Frame(outer, bg="#ffffff", highlightbackground="#dce4ee", highlightthickness=1)
        table_wrap.pack(fill="both", expand=True)
        columns = ("name", "folder", "status")
        self.table = ttk.Treeview(table_wrap, columns=columns, show="headings", selectmode="extended")
        self.table.heading("name", text="视频文件")
        self.table.heading("folder", text="所在文件夹")
        self.table.heading("status", text="状态")
        self.table.column("name", width=250, minwidth=110, stretch=True)
        self.table.column("folder", width=430, minwidth=130, stretch=True)
        self.table.column("status", width=170, minwidth=90, stretch=True)
        y_scrollbar = ttk.Scrollbar(table_wrap, orient="vertical", command=self.table.yview)
        x_scrollbar = ttk.Scrollbar(table_wrap, orient="horizontal", command=self.table.xview)
        self.table.configure(yscrollcommand=y_scrollbar.set, xscrollcommand=x_scrollbar.set)
        y_scrollbar.pack(side="right", fill="y", pady=1)
        x_scrollbar.pack(side="bottom", fill="x", padx=1)
        self.table.pack(side="left", fill="both", expand=True, padx=(1, 0), pady=1)
        self.table.drop_target_register(DND_FILES)
        self.table.dnd_bind("<<Drop>>", self._drop)
        self.table.bind("<Configure>", self._resize_table_columns, add="+")

        output_row = tk.Frame(outer, bg="#f3f6fa")
        output_row.pack(fill="x", pady=(14, 5))
        tk.Label(output_row, text="输出文件夹", bg="#f3f6fa", fg="#1b304b",
                 font=(self.font_family, 10)).pack(side="left")
        self.output_entry = ttk.Entry(output_row, textvariable=self.output)
        self.output_entry.pack(side="left", fill="x", expand=True, padx=10)
        self.folder_button = ttk.Button(output_row, text="选择", command=self._choose_output)
        self.folder_button.pack(side="left")

        settings = ttk.LabelFrame(outer, text="识别设置", padding=(12, 9))
        settings.pack(fill="x", pady=(9, 0))
        fields = [
            ("抽帧间隔（秒）", self.interval, "越小越容易保留短页面"),
            ("PPT 纹理阈值", self.texture, "越大越容易保留实拍画面"),
            ("重复合并阈值", self.duplicate, "越大去重越强"),
            ("最少稳定帧数", self.stable, "越大越少保留短暂画面"),
        ]
        for label, variable, tip in fields:
            cell = tk.Frame(settings, bg="#f3f6fa")
            self.setting_cells.append(cell)
            tk.Label(cell, text=label, bg="#f3f6fa", fg="#30445d",
                     font=(self.font_family, 9)).pack(anchor="w")
            entry = ttk.Entry(cell, textvariable=variable, width=9)
            entry.pack(anchor="w", pady=(3, 0))
            tk.Label(cell, text=tip, bg="#f3f6fa", fg="#7a899b",
                     font=(self.font_family, 8)).pack(anchor="w")
        self.face_check = ttk.Checkbutton(settings, text="启用人脸识别（过滤有人像的画面）",
                                          variable=self.face_detection)
        self.reset_button = ttk.Button(settings, text="恢复默认值", command=self._reset_settings)
        settings.bind("<Configure>", self._schedule_settings_layout, add="+")
        self.setting_entries = [child for child in settings.winfo_children()]

        bottom = tk.Frame(outer, bg="#f3f6fa")
        bottom.pack(fill="x", pady=(13, 7))
        self.start_button = ttk.Button(bottom, text="开始提取", command=self._start)
        self.start_button.pack(side="left")
        ttk.Button(bottom, text="打开输出文件夹", command=self._open_output).pack(side="left", padx=9)
        tk.Label(bottom, textvariable=self.summary, bg="#f3f6fa", fg="#52657b",
                 font=(self.font_family, 9)).pack(side="right")

        progress_row = tk.Frame(outer, bg="#f3f6fa")
        progress_row.pack(fill="x")
        self.progressbar = ttk.Progressbar(progress_row, mode="determinate", maximum=100,
                                           variable=self.progress_value)
        self.progressbar.pack(side="left", fill="x", expand=True, padx=(0, 14))
        tk.Label(progress_row, textvariable=self.eta, bg="#f3f6fa", fg="#65758a",
                 font=(self.font_family, 9), width=25, anchor="e").pack(side="right")

    def _schedule_settings_layout(self, _event=None) -> None:
        if self._settings_layout_after is not None:
            self.root.after_cancel(self._settings_layout_after)
        self._settings_layout_after = self.root.after(80, self._layout_settings)

    def _layout_settings(self) -> None:
        self._settings_layout_after = None
        width = self.face_check.master.winfo_width()
        columns = 4 if width >= 900 else 2 if width >= 560 else 1
        for column in range(4):
            self.face_check.master.columnconfigure(column, weight=1 if column < columns else 0,
                                                   uniform="setting" if column < columns else "")
        for index, cell in enumerate(self.setting_cells):
            cell.grid(row=index // columns, column=index % columns, sticky="ew",
                      padx=(0 if index % columns == 0 else 8, 8), pady=4)

        control_row = (len(self.setting_cells) + columns - 1) // columns
        if columns == 1:
            self.face_check.grid(row=control_row, column=0, sticky="w", pady=(8, 4))
            self.reset_button.grid(row=control_row + 1, column=0, sticky="w", pady=(2, 4))
        else:
            self.face_check.grid(row=control_row, column=0, columnspan=columns - 1,
                                 sticky="w", pady=(8, 4))
            self.reset_button.grid(row=control_row, column=columns - 1,
                                   sticky="e", pady=(8, 4))

    def _resize_table_columns(self, event) -> None:
        width = max(340, event.width - 20)
        name_width = max(110, int(width * .30))
        folder_width = max(130, int(width * .47))
        status_width = max(90, width - name_width - folder_width)
        self.table.column("name", width=name_width)
        self.table.column("folder", width=folder_width)
        self.table.column("status", width=status_width)

    def _reset_settings(self) -> None:
        self.interval.set(DEFAULT_SETTINGS["interval"])
        self.texture.set(DEFAULT_SETTINGS["texture"])
        self.duplicate.set(DEFAULT_SETTINGS["duplicate"])
        self.stable.set(DEFAULT_SETTINGS["stable"])
        self.face_detection.set(DEFAULT_SETTINGS["face_detection"])

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
                       self.folder_button, self.output_entry, self.start_button,
                       self.face_check, self.reset_button):
            widget.configure(state=state)
        for cell in self.setting_entries:
            for widget in cell.winfo_children():
                if isinstance(widget, ttk.Entry):
                    widget.configure(state=state)

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
                "face_detection": self.face_detection.get(),
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
        self.progress_value.set(0)
        self.eta.set("正在估算剩余时间…")
        self.summary.set(f"正在处理 1/{len(self.paths)}")
        threading.Thread(target=self._worker, args=(list(self.paths), output_dir, settings), daemon=True).start()

    def _worker(self, paths: list[Path], output_dir: Path, settings: dict) -> None:
        ok = 0
        durations = []
        for index, path in enumerate(paths, 1):
            started = time.monotonic()
            average = sum(durations) / len(durations) if durations else 60.0
            remaining = average * (len(paths) - index + 1)
            self.events.put(("progress", index - 1, len(paths), remaining))
            self.events.put(("summary", f"正在处理 {index}/{len(paths)}"))
            self.events.put(("status", path, "处理中"))

            def report_progress(message: str, current_path: Path = path,
                                current_index: int = index,
                                estimated_item_time: float = average) -> None:
                self.events.put(("status", current_path, message))
                phase = (0.25 if "抽帧" in message else
                         0.72 if "筛选" in message else
                         0.92 if "PDF" in message else None)
                if phase is not None:
                    completed_units = current_index - 1 + phase
                    left = estimated_item_time * (len(paths) - current_index + 1 - phase)
                    self.events.put(("progress", completed_units, len(paths), max(0, left)))

            try:
                pages, result = extract_one(
                    path, output_dir, settings,
                    progress=report_progress)
                status = f"完成 · {pages} 页" if "已跳过" not in result else f"已有 PDF · {pages} 页"
                self.events.put(("status", path, status))
                ok += 1
            except Exception as exc:
                self.events.put(("status", path, "失败"))
                self.events.put(("error", f"{path.name}：{exc}"))
            durations.append(time.monotonic() - started)
            remaining = (sum(durations) / len(durations)) * (len(paths) - index)
            self.events.put(("progress", index, len(paths), remaining))
        self.events.put(("done", ok, len(paths)))

    @staticmethod
    def _format_eta(seconds: float) -> str:
        if seconds < 60:
            return "预计剩余少于 1 分钟"
        minutes = max(1, round(seconds / 60))
        return f"预计剩余约 {minutes} 分钟"

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
                elif event[0] == "progress":
                    _, completed_units, total, remaining = event
                    self.progress_value.set(completed_units / total * 100 if total else 0)
                    self.eta.set(self._format_eta(remaining) if total else "")
                elif event[0] == "error":
                    messagebox.showerror("提取失败", event[1])
                elif event[0] == "done":
                    self._set_running(False)
                    self.progress_value.set(100 if event[2] else 0)
                    self.eta.set("处理完成")
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
                                        "duplicate": 5.0, "stable": 2,
                                        "face_detection": True})
            return 0
        except Exception:
            output.mkdir(parents=True, exist_ok=True)
            (output / "selftest_error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            return 1
    _enable_windows_dpi_awareness()
    app = ExtractorApp()
    if len(sys.argv) == 2 and sys.argv[1] == "--smoke-gui":
        app.root.after(1500, app.root.destroy)
    app.run()
    return 0


def _enable_windows_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        # PER_MONITOR_AWARE_V2; ignore E_ACCESSDENIED if a manifest already set it.
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except (AttributeError, OSError):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except (AttributeError, OSError):
                pass


if __name__ == "__main__":
    raise SystemExit(main())
