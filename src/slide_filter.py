"""筛选视频中稳定、没有人像的 PPT 页面。"""

from __future__ import annotations

import json
import shutil
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageStat


def signature(path: Path) -> Image.Image:
    with Image.open(path) as image:
        width, height = image.size
        cropped = image.crop((int(width * .03), int(height * .03),
                              int(width * .97), int(height * .97)))
        return cropped.convert("RGB").resize((160, 90), Image.Resampling.BILINEAR)


def difference(left: Image.Image, right: Image.Image) -> tuple[float, float]:
    delta = ImageChops.difference(left, right)
    mean = sum(ImageStat.Stat(delta).mean) / 3
    channels = delta.split()
    greatest = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
    changed = sum(greatest.histogram()[26:]) / (160 * 90)
    return mean, changed


def stable_runs(frames: list[Path], minimum: int) -> list[list[Path]]:
    runs = []
    run = [frames[0]]
    previous = signature(frames[0])
    for path in frames[1:]:
        current = signature(path)
        mean, _ = difference(previous, current)
        if mean < 2:
            run.append(path)
        else:
            if len(run) >= minimum:
                runs.append(run)
            run = [path]
        previous = current
    if len(run) >= minimum:
        runs.append(run)
    return runs


def texture(path: Path) -> float:
    # PPT 的文字和底色通常比实拍画面更平整。
    with Image.open(path) as image:
        small = image.convert("RGB").resize((320, 180), Image.Resampling.BILINEAR)
    blurred = small.filter(ImageFilter.GaussianBlur(3))
    return sum(ImageStat.Stat(ImageChops.difference(small, blurred)).mean) / 3


def course_accent_fraction(path: Path) -> float:
    """识别这组课程片头与 PPT 共用的金黄色版式。"""
    import numpy as np

    with Image.open(path) as image:
        rgb = np.asarray(image.convert("RGB").resize((160, 90)))
    red, green, blue = rgb[:, :, 0].astype(int), rgb[:, :, 1].astype(int), rgb[:, :, 2].astype(int)
    accent = (red > 145) & (green > 100) & (blue < 115) & (red > green * 1.08)
    return float(accent.mean())


def has_face(path: Path, detectors: list) -> bool:
    import cv2
    import numpy as np

    # OpenCV 的 imread 不可靠地处理 Windows 中文路径。
    image = cv2.imdecode(np.frombuffer(path.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return False
    height, width = image.shape[:2]
    image = cv2.resize(image, (640, round(height * 640 / width)))
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return any(len(detector.detectMultiScale(gray, scaleFactor=1.1,
                                              minNeighbors=4, minSize=(24, 24)))
               for detector in detectors)


def select_pages(frames: list[Path], work_dir: Path, identity: dict,
                 texture_threshold: float, duplicate_threshold: float,
                 min_stable_frames: int, force: bool) -> list[Path]:
    import cv2

    state_path = work_dir / "去重进度.json"
    key = {"source": identity, "texture_threshold": texture_threshold,
           "duplicate_threshold": duplicate_threshold,
           "min_stable_frames": min_stable_frames, "algorithm": 5}
    if not force and state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            names = {path.name for path in frames}
            if state.get("key") == key and all(name in names for name in state["pages"]):
                return [work_dir / "抽取帧" / name for name in state["pages"]]
        except (OSError, ValueError, KeyError, TypeError):
            pass

    # Every frame only needs to be decoded once for run detection. Cached signatures
    # also avoid re-reading the selected images during duplicate comparison.
    signatures_by_path = {path: signature(path) for path in frames}
    runs = []
    run = [frames[0]] if frames else []
    for path in frames[1:]:
        mean, _ = difference(signatures_by_path[run[-1]], signatures_by_path[path])
        if mean < 2:
            run.append(path)
        else:
            if len(run) >= min_stable_frames:
                runs.append(run)
            run = [path]
    if len(run) >= min_stable_frames:
        runs.append(run)

    if not runs:
        state = {"key": key, "pages": [], "stable_runs": 0, "candidates": 0}
        temporary = state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(state_path)
        return []

    candidates = []
    with tempfile.TemporaryDirectory(prefix="ppt_faces_") as temporary:
        detectors = []
        for name in ("haarcascade_frontalface_default.xml", "haarcascade_profileface.xml"):
            model = Path(temporary) / name
            shutil.copyfile(Path(cv2.data.haarcascades) / name, model)
            detector = cv2.CascadeClassifier(str(model))
            if detector.empty():
                raise RuntimeError(f"无法加载人脸检测模型：{name}")
            detectors.append(detector)

        cascade_sources = [Path(cv2.data.haarcascades) / name for name in
                           ("haarcascade_frontalface_default.xml", "haarcascade_profileface.xml")]
        worker_state = threading.local()
        run_representatives = [(run, run[len(run) // 2]) for run in runs]
        # First locate the early course title frame with one detector pair.
        title = None
        for _, chosen in run_representatives:
            if int(chosen.stem) * identity["interval"] > 20:
                break
            if texture(chosen) <= 13 and not has_face(chosen, detectors):
                title = chosen
                break

        accent_template = title is not None and course_accent_fraction(title) > .05
        representatives = [chosen for _, chosen in run_representatives
                           if texture(chosen) <= texture_threshold]
        cascade_sources = [Path(cv2.data.haarcascades) / name for name in
                           ("haarcascade_frontalface_default.xml", "haarcascade_profileface.xml")]

        # Worker-local classifiers avoid mutable detector sharing. Do color/face
        # checks concurrently and only after the inexpensive texture filter.
        def worker(path: Path) -> tuple[Path, bool]:
            if not hasattr(worker_state, "detectors"):
                worker_state.detectors = [cv2.CascadeClassifier(str(source)) for source in cascade_sources]
            face = has_face(path, worker_state.detectors)
            accent = course_accent_fraction(path) if accent_template else 1.0
            return path, not face and (not accent_template or accent > .01)

        if representatives:
            with ThreadPoolExecutor(max_workers=min(4, len(representatives))) as pool:
                accepted = dict(pool.map(worker, representatives))
            candidates.extend(path for path in representatives if accepted.get(path, False))
        # 片头也是 PPT 页面；纯实拍视频仍为其保留一页。
        if title is not None and title not in candidates:
            candidates.insert(0, title)

    pages = []
    selected_signatures = []
    for candidate in candidates:
        current = signatures_by_path[candidate]
        if selected_signatures:
            mean, changed = difference(selected_signatures[-1], current)
            if mean <= duplicate_threshold and changed <= .10:
                # 渐进显示的文字、图线只保留最后的完整画面。
                pages[-1], selected_signatures[-1] = candidate, current
                continue
        pages.append(candidate)
        selected_signatures.append(current)

    state = {"key": key, "pages": [path.name for path in pages],
             "stable_runs": len(runs), "candidates": len(candidates)}
    temporary = state_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(state_path)
    return pages
