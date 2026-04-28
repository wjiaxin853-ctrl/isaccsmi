import asyncio
import builtins
import json
import os
import sys
import traceback
from datetime import datetime

import carb.settings
import omni.kit.app
import omni.replicator.core as rep
import omni.timeline
import omni.usd
from pxr import Gf, Usd, UsdGeom

try:
    from isaacsim.core.utils.semantics import add_labels as add_semantic_labels
except Exception:
    add_semantic_labels = None


CAMERA_PATH = "/World/Camera"
OUTPUT_DIR = r"C:\Users\522\Downloads\wjx\outputfinale"
LOG_FILE = os.path.join(OUTPUT_DIR, "synthetic_data_export_log.txt")
ERROR_FILE = os.path.join(OUTPUT_DIR, "synthetic_data_export_error.txt")
RESOLUTION = (1280, 720)
NUM_FRAMES = 200
RT_SUBFRAMES = 0
WARMUP_STEPS = 5
RUN_GUARD_NAME = "_wjx_sdr_full_export_task"

SEMANTIC_ROOT_LABELS = {
    "/World/Obj3d66_1238088_1_934": "train_new",
    "/World/AM223_04": "train_ref",
}

WRITER_PARAMS = {
    "rgb": True,
    "bounding_box_2d_tight": True,
    "bounding_box_2d_loose": True,
    "semantic_segmentation": True,
    "colorize_semantic_segmentation": True,
    "instance_id_segmentation": True,
    "colorize_instance_id_segmentation": True,
    "instance_segmentation": True,
    "colorize_instance_segmentation": True,
    "distance_to_camera": True,
    "distance_to_image_plane": True,
    "bounding_box_3d": True,
    "occlusion": True,
    "normals": True,
    "motion_vectors": True,
    "camera_params": True,
    "pointcloud": True,
    "pointcloud_include_unlabelled": True,
    "skeleton_data": True,
}


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


def write_runtime_metadata():
    ensure_dir(OUTPUT_DIR)
    path = os.path.join(OUTPUT_DIR, "runtime_metadata.json")
    payload = {
        "log_file": LOG_FILE,
        "error_file": ERROR_FILE,
        "camera_path": CAMERA_PATH,
        "resolution": {"width": RESOLUTION[0], "height": RESOLUTION[1]},
        "num_frames": NUM_FRAMES,
        "rt_subframes": RT_SUBFRAMES,
        "warmup_steps": WARMUP_STEPS,
        "writer_params": WRITER_PARAMS,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path


def append_frame_trace(frame_idx, timeline_time):
    path = os.path.join(OUTPUT_DIR, "frame_trace.txt")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"frame={frame_idx:04d}, timeline_time={timeline_time:.6f}\n")


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


def build_camera_pose(stage, camera_path):
    prim = stage.GetPrimAtPath(camera_path)
    if not prim:
        raise RuntimeError(f"找不到相机: {camera_path}")

    camera = UsdGeom.Camera(prim)
    xform_cache = UsdGeom.XformCache()
    world_matrix = xform_cache.GetLocalToWorldTransform(prim)
    world_transform = Gf.Transform(world_matrix)

    return {
        "timestamp": datetime.now().isoformat(),
        "camera_path": camera_path,
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


def export_camera_pose_frame(stage, output_dir, frame_idx):
    ensure_dir(output_dir)
    params = build_camera_pose(stage, CAMERA_PATH)
    params["frame_index"] = frame_idx
    path = os.path.join(output_dir, f"frame_{frame_idx:04d}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(params, f, indent=2, ensure_ascii=False)
    return path


def apply_default_semantics(stage):
    if add_semantic_labels is None:
        print("未找到语义标签工具，跳过语义预处理。")
        return

    applied = 0
    for root_path, label in SEMANTIC_ROOT_LABELS.items():
        root_prim = stage.GetPrimAtPath(root_path)
        if not root_prim:
            continue
        for prim in Usd.PrimRange(root_prim):
            prim_path = str(prim.GetPath())
            if "/Looks" in prim_path:
                continue
            if prim.GetTypeName() not in ("Xform", "Mesh"):
                continue
            try:
                add_semantic_labels(prim, [label], instance_name="class", overwrite=False)
                applied += 1
            except Exception:
                log_exception(f"写入语义标签失败: {prim_path}")

    print(f"语义预处理完成，已尝试写入标签的 Prim 数量: {applied}")


async def wait_for_user_play(timeline, app):
    print("脚本已就绪。请在 Isaac Sim 界面点击 Play，检测到播放后将自动开始导出。")
    while not timeline.is_playing():
        await app.next_update_async()
    print("已检测到 Play，开始导出。")


async def main_async():
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    logger = Tee(LOG_FILE)
    sys.stdout = logger
    sys.stderr = logger

    app = omni.kit.app.get_app()
    timeline = omni.timeline.get_timeline_interface()
    writer = None
    render_product = None
    original_capture_on_play = None
    camera_pose_dir = os.path.join(OUTPUT_DIR, "camera_pose")

    try:
        ensure_dir(OUTPUT_DIR)
        ensure_dir(camera_pose_dir)
        ensure_dir(os.path.dirname(ERROR_FILE))

        if os.path.exists(ERROR_FILE):
            os.remove(ERROR_FILE)
        frame_trace_path = os.path.join(OUTPUT_DIR, "frame_trace.txt")
        if os.path.exists(frame_trace_path):
            os.remove(frame_trace_path)

        print(f"日志文件: {LOG_FILE}")
        print(f"错误文件: {ERROR_FILE}")
        print(f"输出目录: {OUTPUT_DIR}")
        print(f"相机路径: {CAMERA_PATH}")
        print(f"分辨率: {RESOLUTION[0]}x{RESOLUTION[1]}")
        print(f"目标帧数: {NUM_FRAMES}")
        metadata_path = write_runtime_metadata()
        print(f"运行参数文件: {metadata_path}")

        stage = omni.usd.get_context().get_stage()
        if stage is None:
            raise RuntimeError("当前没有打开的 Stage")
        if not stage.GetPrimAtPath(CAMERA_PATH):
            raise RuntimeError(f"Stage 中不存在相机: {CAMERA_PATH}")

        clear_previous_orchestrator(stage)
        apply_default_semantics(stage)

        original_capture_on_play = carb.settings.get_settings().get("/omni/replicator/captureOnPlay")
        if original_capture_on_play:
            rep.orchestrator.set_capture_on_play(False)
            print("已临时关闭 Replicator captureOnPlay，改为脚本控制采集。")

        writer = rep.writers.get("BasicWriter")
        writer.initialize(output_dir=OUTPUT_DIR, **WRITER_PARAMS)
        print("BasicWriter 已初始化。")

        render_product = rep.create.render_product(CAMERA_PATH, RESOLUTION)
        writer.attach([render_product])
        print(f"Render product 已附加: {render_product}")

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
            pose_path = export_camera_pose_frame(stage, camera_pose_dir, captured)
            timeline_time = timeline.get_current_time()
            append_frame_trace(captured, timeline_time)
            print(f"frame={captured:04d}, timeline_time={timeline_time:.6f} -> camera_pose: {pose_path}")
            captured += 1

        await rep.orchestrator.wait_until_complete_async()
        print(f"导出完成，共导出 {captured} 帧。")
        print("BasicWriter 参数:")
        for key, value in WRITER_PARAMS.items():
            print(f"  {key}: {value}")
        print(f"附加相机位姿目录: {camera_pose_dir}")
    except Exception:
        log_exception("导出阶段发生异常:")
        raise
    finally:
        try:
            if writer is not None:
                writer.detach()
        except Exception:
            log_exception("writer.detach() 失败:")

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
    print("已有一个全参数导出任务正在运行，请不要重复执行脚本。先等当前任务结束，或重启 Isaac Sim 后再试。")
else:
    task = asyncio.ensure_future(main_async())
    setattr(builtins, RUN_GUARD_NAME, task)
    task.add_done_callback(on_task_done)
