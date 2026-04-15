import asyncio
import json
import os
import sys
import traceback
from datetime import datetime

import numpy as np
import omni.kit.app
import omni.kit.viewport.utility as viewport_utility
import omni.replicator.core as rep
import omni.timeline
import omni.usd
from PIL import Image
from pxr import Gf, UsdGeom


CAMERA_PATH = "/World/Camera"
OUTPUT_DIR = r"C:\Users\522\Downloads\data\1"
LOG_FILE = r"C:\Users\522\Downloads\data\1output.txt"
RESOLUTION = (1280, 720)
NUM_FRAMES = 30
WARMUP_UPDATES = 10
UPDATES_PER_FRAME = 2

# 主需求优先级: RGB > 点云 / 法线 / 到相机距离 > 其他
ANNOTATOR_SPECS = [
    {
        "name": "distance_to_camera",
        "folder": "distance_to_camera",
        "kind": "scalar_image",
    },
    {
        "name": "distance_to_image_plane",
        "folder": "distance_to_image_plane",
        "kind": "scalar_image",
    },
    {
        "name": "normals",
        "folder": "normals",
        "kind": "vector_image",
    },
    {
        "name": "pointcloud",
        "folder": "pointcloud",
        "kind": "pointcloud",
    },
    {
        "name": "semantic_segmentation",
        "folder": "semantic_segmentation",
        "kind": "label_image",
    },
    {
        "name": "instance_segmentation_fast",
        "folder": "instance_segmentation_fast",
        "kind": "label_image",
    },
    {
        "name": "bounding_box_2d_tight_fast",
        "folder": "bounding_box_2d_tight_fast",
        "kind": "json",
    },
    {
        "name": "bounding_box_3d_fast",
        "folder": "bounding_box_3d_fast",
        "kind": "json",
    },
]


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


class Tee:
    def __init__(self, file_path):
        ensure_dir(os.path.dirname(file_path))
        self.console = sys.stdout
        self.file = open(file_path, "w", encoding="utf-8")

    def write(self, message):
        self.console.write(message)
        self.file.write(message)
        self.file.flush()

    def flush(self):
        self.console.flush()
        self.file.flush()


def log_exception(prefix):
    print(prefix)
    traceback.print_exc()


def matrix_to_list(matrix):
    return [[float(matrix[i][j]) for j in range(4)] for i in range(4)]


def vec3_to_list(vec):
    return [float(vec[0]), float(vec[1]), float(vec[2])]


def quat_to_list(quat):
    imag = quat.GetImaginary()
    return [float(quat.GetReal()), float(imag[0]), float(imag[1]), float(imag[2])]


def compute_intrinsics(camera, width, height):
    focal_length = float(camera.GetFocalLengthAttr().Get())
    horizontal_aperture = float(camera.GetHorizontalApertureAttr().Get())
    vertical_aperture = float(camera.GetVerticalApertureAttr().Get())
    fx = width * focal_length / horizontal_aperture
    fy = height * focal_length / vertical_aperture
    cx = width * 0.5
    cy = height * 0.5
    return {
        "focal_length_mm": focal_length,
        "horizontal_aperture_mm": horizontal_aperture,
        "vertical_aperture_mm": vertical_aperture,
        "fx": fx,
        "fy": fy,
        "cx": cx,
        "cy": cy,
        "width": width,
        "height": height,
    }


def export_camera_params(stage, output_dir):
    prim = stage.GetPrimAtPath(CAMERA_PATH)
    if not prim:
        raise RuntimeError(f"找不到相机: {CAMERA_PATH}")

    camera = UsdGeom.Camera(prim)
    xform_cache = UsdGeom.XformCache()
    world_matrix = xform_cache.GetLocalToWorldTransform(prim)
    world_transform = Gf.Transform(world_matrix)

    params = {
        "export_time": datetime.now().isoformat(),
        "camera_path": CAMERA_PATH,
        "intrinsics": compute_intrinsics(camera, RESOLUTION[0], RESOLUTION[1]),
        "extrinsics": {
            "world_matrix": matrix_to_list(world_matrix),
            "translation": vec3_to_list(world_transform.GetTranslation()),
            "rotation_quat_wxyz": quat_to_list(world_transform.GetRotation().GetQuat()),
        },
        "clip_range": [
            float(camera.GetClippingRangeAttr().Get()[0]),
            float(camera.GetClippingRangeAttr().Get()[1]),
        ],
    }

    params_path = os.path.join(output_dir, "camera_params.json")
    with open(params_path, "w", encoding="utf-8") as f:
        json.dump(params, f, indent=2, ensure_ascii=False)
    print(f"已导出相机参数: {params_path}")


def configure_viewport(viewport_api):
    if viewport_api is None:
        raise RuntimeError("未找到可用 viewport")

    if hasattr(viewport_api, "set_texture_resolution"):
        viewport_api.set_texture_resolution(RESOLUTION)
    elif hasattr(viewport_api, "texture_resolution"):
        viewport_api.texture_resolution = RESOLUTION

    if hasattr(viewport_api, "camera_path"):
        viewport_api.camera_path = CAMERA_PATH
    elif hasattr(viewport_api, "set_active_camera"):
        viewport_api.set_active_camera(CAMERA_PATH)
    else:
        raise RuntimeError("当前 viewport API 不支持设置相机路径")


def get_viewport_render_product_path(viewport_api):
    for attr_name in ("render_product_path", "render_product"):
        if hasattr(viewport_api, attr_name):
            value = getattr(viewport_api, attr_name)
            if isinstance(value, str) and value:
                return value
    return None


async def capture_rgb_frame(viewport_api, output_path):
    result = viewport_utility.capture_viewport_to_file(viewport_api, output_path)
    if asyncio.iscoroutine(result):
        await result
    else:
        for _ in range(5):
            await omni.kit.app.get_app().next_update_async()


def ensure_channel_folders(root_dir):
    folders = {
        "rgb": os.path.join(root_dir, "rgb"),
        "camera_params": os.path.join(root_dir, "camera_params"),
    }
    for spec in ANNOTATOR_SPECS:
        folders[spec["folder"]] = os.path.join(root_dir, spec["folder"])
    for path in folders.values():
        ensure_dir(path)
    return folders


def array_has_data(data):
    if data is None:
        return False
    try:
        return np.array(data).size > 0
    except Exception:
        return False


def normalize_scalar_image(data):
    arr = np.array(data, dtype=np.float32)
    if arr.size == 0:
        return None
    if arr.ndim == 1:
        arr = arr.reshape((RESOLUTION[1], RESOLUTION[0]))
    elif arr.ndim == 3 and arr.shape[-1] == 1:
        arr = arr[..., 0]
    if arr.ndim != 2:
        return None
    return arr


def normalize_vector_image(data):
    arr = np.array(data, dtype=np.float32)
    if arr.size == 0:
        return None
    if arr.ndim == 1:
        channels = arr.size // (RESOLUTION[0] * RESOLUTION[1])
        if channels <= 0:
            return None
        arr = arr.reshape((RESOLUTION[1], RESOLUTION[0], channels))
    elif arr.ndim == 2:
        arr = arr[..., None]
    if arr.ndim != 3:
        return None
    if arr.shape[-1] > 3:
        arr = arr[..., :3]
    if arr.shape[-1] == 1:
        arr = np.repeat(arr, 3, axis=-1)
    if arr.shape[-1] != 3:
        return None
    return arr


def save_scalar_image(data, folder_path, frame_idx):
    arr = normalize_scalar_image(data)
    if arr is None:
        return False

    base = os.path.join(folder_path, f"frame_{frame_idx:04d}")
    np.save(base + ".npy", arr)

    valid_mask = np.isfinite(arr)
    vis = np.zeros_like(arr, dtype=np.uint8)
    if np.any(valid_mask):
        valid = arr[valid_mask]
        arr_min = float(valid.min())
        arr_max = float(valid.max())
        if arr_max - arr_min > 1e-6:
            norm = np.clip((arr - arr_min) / (arr_max - arr_min), 0.0, 1.0)
            vis = (norm * 255.0).astype(np.uint8)
    Image.fromarray(vis).save(base + ".png")
    return True


def save_vector_image(data, folder_path, frame_idx):
    arr = normalize_vector_image(data)
    if arr is None:
        return False

    base = os.path.join(folder_path, f"frame_{frame_idx:04d}")
    np.save(base + ".npy", arr)
    vis = np.clip((arr + 1.0) * 0.5, 0.0, 1.0)
    vis = np.ascontiguousarray((vis * 255.0).astype(np.uint8))
    Image.fromarray(vis).save(base + ".png")
    return True


def save_label_image(data, folder_path, frame_idx):
    arr = np.array(data)
    if arr.size == 0:
        return False
    if arr.ndim == 1:
        arr = arr.reshape((RESOLUTION[1], RESOLUTION[0]))
    elif arr.ndim == 3 and arr.shape[-1] == 1:
        arr = arr[..., 0]
    if arr.ndim != 2:
        return False

    base = os.path.join(folder_path, f"frame_{frame_idx:04d}")
    np.save(base + ".npy", arr)
    ids = arr.astype(np.int64)
    vis = np.stack(
        [
            (ids * 53) % 255,
            (ids * 97) % 255,
            (ids * 193) % 255,
        ],
        axis=-1,
    ).astype(np.uint8)
    Image.fromarray(vis).save(base + ".png")
    return True


def save_pointcloud(data, folder_path, frame_idx):
    base = os.path.join(folder_path, f"frame_{frame_idx:04d}")

    if isinstance(data, dict):
        with open(base + ".json", "w", encoding="utf-8") as f:
            json.dump(to_jsonable(data), f, indent=2, ensure_ascii=False)

        candidate_keys = (
            "data",
            "points",
            "pointcloud",
            "data_points",
            "vertices",
            "xyz",
        )
        points = None
        for key in candidate_keys:
            if key in data:
                points = data[key]
                break

        if points is None:
            return True

        arr = np.array(points, dtype=np.float32)
    else:
        arr = np.array(data, dtype=np.float32)

    if arr.size == 0:
        return False

    if arr.ndim == 3:
        arr = arr.reshape((-1, arr.shape[-1]))
    elif arr.ndim == 1:
        if arr.size % 3 != 0:
            return False
        arr = arr.reshape((-1, 3))

    if arr.ndim != 2 or arr.shape[-1] < 3:
        return False

    xyz = arr[:, :3]
    np.save(base + ".npy", xyz)
    return True


def to_jsonable(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    return value


def save_json_data(data, folder_path, frame_idx):
    if data is None:
        return False
    base = os.path.join(folder_path, f"frame_{frame_idx:04d}.json")
    with open(base, "w", encoding="utf-8") as f:
        json.dump(to_jsonable(data), f, indent=2, ensure_ascii=False)
    return True


def save_channel_data(kind, data, folder_path, frame_idx):
    if kind == "scalar_image":
        return save_scalar_image(data, folder_path, frame_idx)
    if kind == "vector_image":
        return save_vector_image(data, folder_path, frame_idx)
    if kind == "label_image":
        return save_label_image(data, folder_path, frame_idx)
    if kind == "pointcloud":
        return save_pointcloud(data, folder_path, frame_idx)
    if kind == "json":
        return save_json_data(data, folder_path, frame_idx)
    return False


async def main_async():
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    logger = Tee(LOG_FILE)
    sys.stdout = logger
    sys.stderr = logger

    timeline = omni.timeline.get_timeline_interface()
    app = omni.kit.app.get_app()
    channel_annotators = []

    try:
        folders = ensure_channel_folders(OUTPUT_DIR)
        print(f"日志文件: {LOG_FILE}")
        print(f"输出目录: {OUTPUT_DIR}")

        stage = omni.usd.get_context().get_stage()
        if stage is None:
            raise RuntimeError("当前没有打开的 Stage")
        if not stage.GetPrimAtPath(CAMERA_PATH):
            raise RuntimeError(f"Stage 中不存在相机: {CAMERA_PATH}")

        export_camera_params(stage, folders["camera_params"])

        viewport_api = viewport_utility.get_active_viewport()
        configure_viewport(viewport_api)
        print(f"当前 viewport 已切换到相机: {CAMERA_PATH}")

        render_product_path = get_viewport_render_product_path(viewport_api)
        print(f"viewport render product: {render_product_path}")

        if render_product_path:
            for spec in ANNOTATOR_SPECS:
                try:
                    annotator = rep.AnnotatorRegistry.get_annotator(spec["name"])
                    annotator.attach([render_product_path])
                    channel_annotators.append((spec, annotator))
                    print(f"已附加 annotator: {spec['name']}")
                except Exception:
                    log_exception(f"附加 annotator 失败: {spec['name']}")

        timeline.play()
        print("时间线已开始播放，开始导出多通道数据...")

        for warmup_idx in range(WARMUP_UPDATES):
            await app.next_update_async()
            print(f"warmup={warmup_idx + 1}/{WARMUP_UPDATES}")

        for frame_idx in range(NUM_FRAMES):
            for _ in range(UPDATES_PER_FRAME):
                await app.next_update_async()

            rgb_path = os.path.join(folders["rgb"], f"frame_{frame_idx:04d}.png")
            await capture_rgb_frame(viewport_api, rgb_path)
            print(f"rgb frame={frame_idx:04d} -> {rgb_path}")

            for spec, annotator in channel_annotators:
                try:
                    data = annotator.get_data()
                    ok = save_channel_data(
                        spec["kind"],
                        data,
                        folders[spec["folder"]],
                        frame_idx,
                    )
                    print(
                        f"{spec['name']} frame={frame_idx:04d} -> "
                        f"{'ok' if ok else 'empty'}"
                    )
                except Exception:
                    log_exception(f"保存通道失败: {spec['name']} frame={frame_idx:04d}")

        print(f"导出完成，共 {NUM_FRAMES} 帧。")
        print("通道目录:")
        for name, path in sorted(folders.items()):
            print(f"  {name}: {path}")
    except Exception:
        log_exception("导出阶段发生异常:")
        raise
    finally:
        try:
            timeline.stop()
        except Exception:
            log_exception("停止时间线时发生异常:")

        for spec, annotator in channel_annotators:
            try:
                annotator.detach()
            except Exception:
                log_exception(f"解绑 annotator 失败: {spec['name']}")

        print("导出完成，时间线已停止。")
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        logger.file.close()


def on_task_done(task):
    try:
        task.result()
    except Exception:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write("异步任务发生未捕获异常:\n")
            f.write(traceback.format_exc())


task = asyncio.ensure_future(main_async())
task.add_done_callback(on_task_done)
