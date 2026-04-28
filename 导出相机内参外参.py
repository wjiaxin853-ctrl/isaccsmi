import json
import math
import os
import sys
import traceback
from datetime import datetime

import numpy as np
import omni.usd
from pxr import Gf, UsdGeom


CAMERA_PATH = "/World/Camera"
OUTPUT_DIR = r"C:\Users\522\Downloads\data\1"
OUTPUT_JSON = os.path.join(OUTPUT_DIR, "camera_parameters.json")
LOG_FILE = r"C:\Users\522\Downloads\data\output.txt"
FALLBACK_RESOLUTION = (1280, 720)


class Tee:
    def __init__(self, file_path):
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        self.console = sys.stdout
        self.file = open(file_path, "w", encoding="utf-8")

    def write(self, message):
        self.console.write(message)
        self.file.write(message)
        self.file.flush()

    def flush(self):
        self.console.flush()
        self.file.flush()


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


def list_all_cameras(stage):
    cameras = []
    for prim in stage.Traverse():
        if prim.IsA(UsdGeom.Camera):
            cameras.append(str(prim.GetPath()))
    return cameras


def get_camera_resolution(stage, camera_path):
    for prim in stage.Traverse():
        if prim.GetTypeName() != "RenderProduct":
            continue

        camera_rel = prim.GetRelationship("camera")
        if not camera_rel:
            continue

        targets = camera_rel.GetTargets()
        if not targets or str(targets[0]) != camera_path:
            continue

        resolution_attr = prim.GetAttribute("resolution")
        if resolution_attr and resolution_attr.HasAuthoredValue():
            value = resolution_attr.Get()
            if value and len(value) == 2:
                return int(value[0]), int(value[1]), str(prim.GetPath())

    return FALLBACK_RESOLUTION[0], FALLBACK_RESOLUTION[1], None


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


def build_camera_params(stage, camera_path):
    camera_prim = stage.GetPrimAtPath(camera_path)
    if not camera_prim:
        raise RuntimeError(f"找不到相机: {camera_path}")
    if not camera_prim.IsA(UsdGeom.Camera):
        raise RuntimeError(f"{camera_path} 不是 Camera 类型")

    camera = UsdGeom.Camera(camera_prim)
    width, height, render_product_path = get_camera_resolution(stage, camera_path)

    xform_cache = UsdGeom.XformCache()
    camera_to_world_gf = xform_cache.GetLocalToWorldTransform(camera_prim)
    world_transform = Gf.Transform(camera_to_world_gf)

    # USD / Gf 默认是行向量矩阵约定，平移在最后一行。
    # 为了和 OpenCV / 机器人常用 4x4 约定一致，这里同时导出：
    # 1. 原始 USD 行主序矩阵
    # 2. 转置后的标准 column-vector 4x4 矩阵
    camera_to_world_usd = np.array(camera_to_world_gf, dtype=np.float64)
    camera_to_world = camera_to_world_usd.T
    world_to_camera = np.linalg.inv(camera_to_world)

    rotation_world = camera_to_world[:3, :3]
    translation_world = np.array(world_transform.GetTranslation(), dtype=np.float64)
    rotation_extrinsic = world_to_camera[:3, :3]
    translation_extrinsic = world_to_camera[:3, 3]

    clip_range = camera.GetClippingRangeAttr().Get()
    intrinsics = compute_intrinsics(camera, width, height)

    return {
        "export_time": datetime.now().isoformat(),
        "stage_path": stage.GetRootLayer().realPath,
        "camera_name": camera_path.split("/")[-1],
        "camera_path": camera_path,
        "render_product_path": render_product_path,
        "intrinsics": intrinsics,
        "extrinsics": {
            "camera_to_world_4x4": camera_to_world.tolist(),
            "camera_to_world_usd_row_major_4x4": camera_to_world_usd.tolist(),
            "world_to_camera_4x4": world_to_camera.tolist(),
            "rotation_matrix_R": rotation_extrinsic.tolist(),
            "translation_vector_t": translation_extrinsic.tolist(),
            "camera_position_world": translation_world.tolist(),
            "camera_orientation_quat_wxyz": quat_to_list(
                Gf.Transform(camera_to_world_gf).GetRotation().GetQuat()
            ),
            "camera_orientation_euler_xyz_degrees": rotation_matrix_to_euler_xyz_degrees(
                rotation_world
            ),
        },
        "clip_range": [float(clip_range[0]), float(clip_range[1])],
    }


def main():
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    logger = Tee(LOG_FILE)
    sys.stdout = logger
    sys.stderr = logger

    try:
        print(f"相机路径: {CAMERA_PATH}")
        print(f"参数输出: {OUTPUT_JSON}")
        print(f"日志输出: {LOG_FILE}")

        stage = omni.usd.get_context().get_stage()
        if stage is None:
            raise RuntimeError("当前没有打开的 Stage")

        cameras = list_all_cameras(stage)
        print(f"场景相机数量: {len(cameras)}")
        for camera_path in cameras:
            print(f"  camera: {camera_path}")

        params = build_camera_params(stage, CAMERA_PATH)

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(params, f, indent=2, ensure_ascii=False)

        print(f"已导出相机参数: {OUTPUT_JSON}")
        print("内参:")
        print(json.dumps(params["intrinsics"], indent=2, ensure_ascii=False))
        print("外参:")
        print(json.dumps(params["extrinsics"], indent=2, ensure_ascii=False))
    except Exception:
        print("导出相机参数失败:")
        traceback.print_exc()
        raise
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        logger.file.close()


main()
