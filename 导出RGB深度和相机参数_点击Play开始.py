import asyncio
import builtins
import json
import math
import os
import shutil
import sys
import traceback

import carb.settings
import numpy as np
import omni.kit.app
import omni.replicator.core as rep
import omni.timeline
import omni.usd
from PIL import Image
from pxr import Gf, UsdGeom


CAMERA_PATH = "/World/Camera"
OUTPUT_DIR = r"C:\Users\522\Downloads\wjx\output-two"
RGB_DIR = os.path.join(OUTPUT_DIR, "rgb")
DEPTH_CAMERA_DIR = os.path.join(OUTPUT_DIR, "distance_to_camera")
DEPTH_IMAGE_PLANE_DIR = os.path.join(OUTPUT_DIR, "distance_to_image_plane")
JSON_DIR = os.path.join(OUTPUT_DIR, "json")
LOG_FILE = os.path.join(OUTPUT_DIR, "export_log.txt")
ERROR_FILE = os.path.join(OUTPUT_DIR, "export_error.txt")
FRAME_TRACE_FILE = os.path.join(OUTPUT_DIR, "frame_trace.txt")
RESOLUTION = (1280, 720)
NUM_FRAMES = 200
RT_SUBFRAMES = 0
WARMUP_STEPS = 5
RUN_GUARD_NAME = "_wjx_rgb_depth_json_export_task"
DEPTH_TYPES = ("distance_to_camera", "distance_to_image_plane")
DEPTH_PNG_SCALE = 1000.0


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


def append_error_log(prefix):
    ensure_dir(os.path.dirname(ERROR_FILE))
    with open(ERROR_FILE, "a", encoding="utf-8") as f:
        f.write(f"{prefix}\n")
        f.write(traceback.format_exc())
        f.write("\n")


def log_exception(prefix):
    print(prefix)
    traceback.print_exc()
    append_error_log(prefix)


def clear_previous_orchestrator(stage):
    try:
        rep.orchestrator.stop()
    except Exception:
        pass

    orchestrator_prim = stage.GetPrimAtPath("/Orchestrator")
    if orchestrator_prim and orchestrator_prim.IsValid():
        stage.RemovePrim("/Orchestrator")
        print("检测到旧的 /Orchestrator，已移除。")


def existing_task_is_running():
    task = getattr(builtins, RUN_GUARD_NAME, None)
    return task is not None and not task.done()


def clean_output_dirs():
    ensure_dir(OUTPUT_DIR)
    for path in (RGB_DIR, DEPTH_CAMERA_DIR, DEPTH_IMAGE_PLANE_DIR, JSON_DIR):
        if os.path.isdir(path):
            shutil.rmtree(path)
        ensure_dir(path)

    for path in (LOG_FILE, ERROR_FILE, FRAME_TRACE_FILE):
        if os.path.exists(path):
            os.remove(path)


def append_frame_trace(frame_idx, timeline_time):
    with open(FRAME_TRACE_FILE, "a", encoding="utf-8") as f:
        f.write(f"frame={frame_idx:04d}, timeline_time={timeline_time:.6f}\n")


def matrix4_to_nested_list(matrix):
    return [[float(matrix[row][col]) for col in range(4)] for row in range(4)]


def matrix3_to_nested_list(matrix):
    return [[float(matrix[row][col]) for col in range(3)] for row in range(3)]


def vec3_to_list(vec):
    return [float(vec[0]), float(vec[1]), float(vec[2])]


def quat_to_list(quat):
    imag = quat.GetImaginary()
    return [float(quat.GetReal()), float(imag[0]), float(imag[1]), float(imag[2])]


def rotation_matrix_to_euler_xyz_degrees(rotation):
    sy = math.sqrt(rotation[0, 0] ** 2 + rotation[1, 0] ** 2)
    singular = sy < 1e-6

    if not singular:
        x = math.atan2(rotation[2, 1], rotation[2, 2])
        y = math.atan2(-rotation[2, 0], sy)
        z = math.atan2(rotation[1, 0], rotation[0, 0])
    else:
        x = math.atan2(-rotation[1, 2], rotation[1, 1])
        y = math.atan2(-rotation[2, 0], sy)
        z = 0.0

    return {
        "roll": math.degrees(x),
        "pitch": math.degrees(y),
        "yaw": math.degrees(z),
    }


def compute_intrinsics(camera, width, height):
    focal_length_mm = float(camera.GetFocalLengthAttr().Get())
    horizontal_aperture_mm = float(camera.GetHorizontalApertureAttr().Get())
    vertical_aperture_mm = float(camera.GetVerticalApertureAttr().Get())
    horizontal_offset_mm = float(camera.GetHorizontalApertureOffsetAttr().Get() or 0.0)
    vertical_offset_mm = float(camera.GetVerticalApertureOffsetAttr().Get() or 0.0)

    fx = (focal_length_mm / horizontal_aperture_mm) * width
    fy = (focal_length_mm / vertical_aperture_mm) * height
    cx = (width * 0.5) + (horizontal_offset_mm / horizontal_aperture_mm) * width
    cy = (height * 0.5) + (vertical_offset_mm / vertical_aperture_mm) * height

    k_matrix = np.array(
        [
            [fx, 0.0, cx],
            [0.0, fy, cy],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )

    return {
        "fx": float(fx),
        "fy": float(fy),
        "cx": float(cx),
        "cy": float(cy),
        "intrinsics_matrix_K": matrix3_to_nested_list(k_matrix),
        "focal_length_mm": focal_length_mm,
        "horizontal_aperture_mm": horizontal_aperture_mm,
        "vertical_aperture_mm": vertical_aperture_mm,
        "horizontal_aperture_offset_mm": horizontal_offset_mm,
        "vertical_aperture_offset_mm": vertical_offset_mm,
        "image_width": int(width),
        "image_height": int(height),
        "distortion_model": "pinhole",
        "distortion_coefficients": [0.0, 0.0, 0.0, 0.0, 0.0],
    }


def export_camera_params(stage):
    camera_prim = stage.GetPrimAtPath(CAMERA_PATH)
    if not camera_prim:
        raise RuntimeError(f"找不到相机: {CAMERA_PATH}")
    if not camera_prim.IsA(UsdGeom.Camera):
        raise RuntimeError(f"{CAMERA_PATH} 不是 Camera 类型")

    camera = UsdGeom.Camera(camera_prim)
    xform_cache = UsdGeom.XformCache()
    camera_to_world_gf = xform_cache.GetLocalToWorldTransform(camera_prim)
    world_transform = Gf.Transform(camera_to_world_gf)

    camera_to_world_usd = np.array(camera_to_world_gf, dtype=np.float64)
    camera_to_world = camera_to_world_usd.T
    world_to_camera = np.linalg.inv(camera_to_world)
    rotation_world = camera_to_world[:3, :3]
    translation_world = np.array(world_transform.GetTranslation(), dtype=np.float64)
    rotation_extrinsic = world_to_camera[:3, :3]
    translation_extrinsic = world_to_camera[:3, 3]
    clip_range = camera.GetClippingRangeAttr().Get()

    payload = {
        "camera_path": CAMERA_PATH,
        "resolution": {"width": RESOLUTION[0], "height": RESOLUTION[1]},
        "depth_types": list(DEPTH_TYPES),
        "intrinsics": compute_intrinsics(camera, RESOLUTION[0], RESOLUTION[1]),
        "extrinsics": {
            "camera_to_world_4x4": camera_to_world.tolist(),
            "camera_to_world_usd_row_major_4x4": camera_to_world_usd.tolist(),
            "world_to_camera_4x4": world_to_camera.tolist(),
            "rotation_matrix_R": rotation_extrinsic.tolist(),
            "translation_vector_t": translation_extrinsic.tolist(),
            "camera_position_world": translation_world.tolist(),
            "camera_orientation_quat_wxyz": quat_to_list(world_transform.GetRotation().GetQuat()),
            "camera_orientation_euler_xyz_degrees": rotation_matrix_to_euler_xyz_degrees(rotation_world),
        },
        "clip_range": [float(clip_range[0]), float(clip_range[1])],
    }

    output_path = os.path.join(JSON_DIR, "camera_parameters.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"已导出相机参数: {output_path}")
    return output_path


def save_rgb_image(rgb_data, frame_idx):
    arr = np.asarray(rgb_data)
    if arr.ndim != 3:
        raise RuntimeError(f"RGB 数据维度异常: {arr.shape}")
    if arr.shape[2] >= 3:
        arr = arr[:, :, :3]
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    output_path = os.path.join(RGB_DIR, f"frame_{frame_idx:04d}.png")
    Image.fromarray(arr, mode="RGB").save(output_path)
    return output_path


def save_depth_outputs(depth_data, frame_idx, output_dir):
    arr = np.asarray(depth_data)
    if arr.ndim == 3 and arr.shape[2] == 1:
        arr = arr[:, :, 0]
    if arr.ndim != 2:
        raise RuntimeError(f"深度数据维度异常: {arr.shape}")

    arr = arr.astype(np.float32, copy=False)
    npy_path = os.path.join(output_dir, f"frame_{frame_idx:04d}.npy")
    np.save(npy_path, arr)

    valid_mask = np.isfinite(arr)
    if np.any(valid_mask):
        valid_values = arr[valid_mask]
        vmin = float(np.min(valid_values))
        vmax = float(np.max(valid_values))
    else:
        vmin = None
        vmax = None
    safe_arr = np.nan_to_num(arr, nan=0.0, posinf=65535.0 / DEPTH_PNG_SCALE, neginf=0.0)
    safe_arr = np.clip(safe_arr * DEPTH_PNG_SCALE, 0.0, 65535.0)
    png_data = safe_arr.astype(np.uint16)

    png_path = os.path.join(output_dir, f"frame_{frame_idx:04d}.png")
    Image.fromarray(png_data).save(png_path)
    return npy_path, png_path, vmin, vmax


async def wait_for_user_play(timeline, app):
    print("脚本已就绪。请在 Isaac Sim 界面点击 Play，检测到播放后将自动开始导出。")
    while not timeline.is_playing():
        await app.next_update_async()
    print("已检测到 Play，开始导出。")


async def main_async():
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    clean_output_dirs()
    logger = Tee(LOG_FILE)
    sys.stdout = logger
    sys.stderr = logger

    app = omni.kit.app.get_app()
    timeline = omni.timeline.get_timeline_interface()
    render_product = None
    rgb_annotator = None
    depth_annotators = {}
    original_capture_on_play = None

    try:
        print(f"日志文件: {LOG_FILE}")
        print(f"错误文件: {ERROR_FILE}")
        print(f"输出目录: {OUTPUT_DIR}")
        print(f"RGB目录: {RGB_DIR}")
        print(f"距离到相机目录: {DEPTH_CAMERA_DIR}")
        print(f"距离到相机平面目录: {DEPTH_IMAGE_PLANE_DIR}")
        print(f"JSON目录: {JSON_DIR}")
        print(f"相机路径: {CAMERA_PATH}")
        print(f"分辨率: {RESOLUTION[0]}x{RESOLUTION[1]}")
        print(f"目标帧数: {NUM_FRAMES}")
        print(f"深度类型: {', '.join(DEPTH_TYPES)}")

        stage = omni.usd.get_context().get_stage()
        if stage is None:
            raise RuntimeError("当前没有打开的 Stage")
        if not stage.GetPrimAtPath(CAMERA_PATH):
            raise RuntimeError(f"Stage 中不存在相机: {CAMERA_PATH}")

        export_camera_params(stage)
        clear_previous_orchestrator(stage)

        original_capture_on_play = carb.settings.get_settings().get("/omni/replicator/captureOnPlay")
        if original_capture_on_play:
            rep.orchestrator.set_capture_on_play(False)
            print("已临时关闭 Replicator captureOnPlay，改为脚本控制采集。")

        render_product = rep.create.render_product(CAMERA_PATH, RESOLUTION)
        rgb_annotator = rep.AnnotatorRegistry.get_annotator("rgb")
        rgb_annotator.attach(render_product)
        for depth_type in DEPTH_TYPES:
            annotator = rep.AnnotatorRegistry.get_annotator(depth_type)
            annotator.attach(render_product)
            depth_annotators[depth_type] = annotator
        print(f"Render product 已附加: {render_product}")
        print("已附加 annotator: rgb")
        for depth_type in DEPTH_TYPES:
            print(f"已附加 annotator: {depth_type}")

        await wait_for_user_play(timeline, app)

        for warmup_idx in range(WARMUP_STEPS):
            await rep.orchestrator.step_async(rt_subframes=RT_SUBFRAMES, delta_time=None, pause_timeline=False)
            print(f"warmup={warmup_idx + 1}/{WARMUP_STEPS}, timeline_time={timeline.get_current_time():.6f}")

        captured = 0
        while captured < NUM_FRAMES:
            if not timeline.is_playing():
                print(f"检测到时间线已停止，提前结束在 frame={captured:04d}")
                break

            await rep.orchestrator.step_async(rt_subframes=RT_SUBFRAMES, delta_time=None, pause_timeline=False)
            timeline_time = timeline.get_current_time()
            append_frame_trace(captured, timeline_time)

            rgb_data = rgb_annotator.get_data()
            rgb_path = save_rgb_image(rgb_data, captured)

            depth_logs = []
            for depth_type in DEPTH_TYPES:
                output_dir = DEPTH_CAMERA_DIR if depth_type == "distance_to_camera" else DEPTH_IMAGE_PLANE_DIR
                depth_data = depth_annotators[depth_type].get_data()
                npy_path, png_path, depth_min, depth_max = save_depth_outputs(depth_data, captured, output_dir)
                depth_logs.append(
                    f"{depth_type}:png={os.path.basename(png_path)},npy={os.path.basename(npy_path)},min={depth_min},max={depth_max}"
                )

            print(
                f"frame={captured:04d}, timeline_time={timeline_time:.6f}, "
                f"rgb={os.path.basename(rgb_path)}, " + " | ".join(depth_logs)
            )
            captured += 1

        await rep.orchestrator.wait_until_complete_async()
        print(f"导出完成，共导出 {captured} 帧。")
        print("输出目录:")
        print(f"  rgb: {RGB_DIR}")
        print(f"  distance_to_camera: {DEPTH_CAMERA_DIR}")
        print(f"  distance_to_image_plane: {DEPTH_IMAGE_PLANE_DIR}")
        print(f"  json: {JSON_DIR}")
    except Exception:
        log_exception("导出阶段发生异常:")
        raise
    finally:
        try:
            if rgb_annotator is not None:
                rgb_annotator.detach()
        except Exception:
            log_exception("rgb annotator detach 失败:")

        try:
            for annotator in depth_annotators.values():
                annotator.detach()
        except Exception:
            log_exception("depth annotator detach 失败:")

        try:
            if render_product is not None and hasattr(render_product, "destroy"):
                render_product.destroy()
        except Exception:
            log_exception("销毁 render product 失败:")

        try:
            if original_capture_on_play is not None:
                rep.orchestrator.set_capture_on_play(original_capture_on_play)
        except Exception:
            log_exception("恢复 captureOnPlay 失败:")

        print("导出流程结束。")
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        logger.file.close()


def on_task_done(task):
    try:
        task.result()
    except Exception:
        ensure_dir(os.path.dirname(LOG_FILE))
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write("异步任务发生未捕获异常:\n")
            f.write(traceback.format_exc())
            f.write("\n")
        append_error_log("异步任务发生未捕获异常:")
    finally:
        current = getattr(builtins, RUN_GUARD_NAME, None)
        if current is task:
            setattr(builtins, RUN_GUARD_NAME, None)


if existing_task_is_running():
    print("已有一个导出任务正在运行，请不要重复执行脚本。先等当前任务结束，或重启 Isaac Sim 后再试。")
else:
    task = asyncio.ensure_future(main_async())
    setattr(builtins, RUN_GUARD_NAME, task)
    task.add_done_callback(on_task_done)
