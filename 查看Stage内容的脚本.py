import os
import traceback

import carb
import omni.usd
from pxr import Usd, UsdGeom, UsdLux, UsdPhysics, UsdShade


DEFAULT_OUTPUT_FILE = r"C:\Users\522\Downloads\wjx\1output.txt"
OUTPUT_FILE = os.environ.get("STAGE_DIAGNOSTIC_OUTPUT", DEFAULT_OUTPUT_FILE)
MAX_VALUE_LEN = 400
LIGHT_TYPE_NAMES = {
    "CylinderLight",
    "DiskLight",
    "DistantLight",
    "DomeLight",
    "GeometryLight",
    "PortalLight",
    "RectLight",
    "SphereLight",
}


def reset_output():
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("")


def log(message=""):
    text = str(message)
    try:
        carb.log_info(text)
    except Exception:
        pass

    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        f.write(text + "\n")


def format_value(value):
    if value is None:
        return "None"

    try:
        text = str(value)
    except Exception:
        text = repr(value)

    text = text.replace("\n", " ")
    if len(text) > MAX_VALUE_LEN:
        text = text[:MAX_VALUE_LEN] + "... <已截断>"
    return text


def safe_get_attribute_value(attr):
    try:
        if attr.HasAuthoredValue():
            return attr.Get()
        connections = attr.GetConnections()
        if connections:
            return f"<连接到 {len(connections)} 个目标>"
    except Exception:
        pass
    return None


def is_light_prim(prim):
    light_schema = getattr(UsdLux, "Light", None)
    if light_schema is not None:
        try:
            if prim.IsA(light_schema):
                return True
        except Exception:
            pass

    return prim.GetTypeName() in LIGHT_TYPE_NAMES


def describe_material_binding(prim, indent):
    try:
        binding_api = UsdShade.MaterialBindingAPI(prim)
    except Exception:
        return

    try:
        direct_rel = binding_api.GetDirectBindingRel()
        targets = direct_rel.GetTargets() if direct_rel else []
        if targets:
            log(f"{indent}直接材质绑定: {[str(t) for t in targets]}")
    except Exception:
        pass

    try:
        material, _ = binding_api.ComputeBoundMaterial()
        if material:
            log(f"{indent}解析后材质: {material.GetPath()}")
    except Exception:
        pass


def describe_physics_apis(prim, indent):
    api_names = []

    try:
        if prim.HasAPI(UsdPhysics.RigidBodyAPI):
            api_names.append("RigidBodyAPI")
    except Exception:
        pass

    try:
        if prim.HasAPI(UsdPhysics.CollisionAPI):
            api_names.append("CollisionAPI")
    except Exception:
        pass

    try:
        if prim.HasAPI(UsdPhysics.MassAPI):
            api_names.append("MassAPI")
    except Exception:
        pass

    try:
        if prim.HasAPI(UsdPhysics.DriveAPI):
            api_names.append("DriveAPI")
    except Exception:
        pass

    if api_names:
        log(f"{indent}物理API: {', '.join(api_names)}")


def describe_xform(prim, indent, xform_cache):
    if not prim.IsA(UsdGeom.Xformable):
        return

    try:
        xformable = UsdGeom.Xformable(prim)
        ops = xformable.GetOrderedXformOps()
        if ops:
            log(f"{indent}XformOps ({len(ops)}):")
            for op in ops:
                try:
                    op_value = op.Get()
                except Exception:
                    op_value = "<读取失败>"
                log(
                    f"{indent}  - {op.GetName()} | type={op.GetOpType()} | value={format_value(op_value)}"
                )
    except Exception:
        log(f"{indent}XformOps: <读取失败>")

    try:
        world_matrix = xform_cache.GetLocalToWorldTransform(prim)
        world_translation = world_matrix.ExtractTranslation()
        log(f"{indent}世界平移: {format_value(world_translation)}")
        log(f"{indent}世界矩阵: {format_value(world_matrix)}")
    except Exception:
        log(f"{indent}世界变换: <读取失败>")


def describe_bounds(prim, indent, bbox_cache):
    if not prim.IsA(UsdGeom.Imageable):
        return

    try:
        world_bound = bbox_cache.ComputeWorldBound(prim)
        aligned_box = world_bound.ComputeAlignedBox()
        log(f"{indent}世界包围盒最小值: {format_value(aligned_box.GetMin())}")
        log(f"{indent}世界包围盒最大值: {format_value(aligned_box.GetMax())}")
    except Exception:
        log(f"{indent}世界包围盒: <读取失败>")


def describe_mesh(prim, indent):
    if prim.GetTypeName() != "Mesh":
        return

    try:
        mesh = UsdGeom.Mesh(prim)
        points = mesh.GetPointsAttr().Get()
        face_counts = mesh.GetFaceVertexCountsAttr().Get()
        face_indices = mesh.GetFaceVertexIndicesAttr().Get()

        log(f"{indent}顶点数: {len(points) if points else 0}")
        log(f"{indent}面数: {len(face_counts) if face_counts else 0}")
        log(f"{indent}索引数: {len(face_indices) if face_indices else 0}")
    except Exception:
        log(f"{indent}Mesh数据: <读取失败>")

    geom_subsets = [child for child in prim.GetChildren() if child.GetTypeName() == "GeomSubset"]
    if geom_subsets:
        log(f"{indent}GeomSubset 数量: {len(geom_subsets)}")
        for subset in geom_subsets:
            log(f"{indent}  - {subset.GetName()} -> {subset.GetPath()}")
            describe_material_binding(subset, indent + "    ")


def describe_light_or_camera(prim, indent):
    prim_type = prim.GetTypeName()

    if is_light_prim(prim):
        try:
            intensity_attr = prim.GetAttribute("intensity")
            color_attr = prim.GetAttribute("color")
            exposure_attr = prim.GetAttribute("exposure")
            log(f"{indent}光源强度: {format_value(intensity_attr.Get() if intensity_attr else None)}")
            log(f"{indent}光源颜色: {format_value(color_attr.Get() if color_attr else None)}")
            log(f"{indent}曝光: {format_value(exposure_attr.Get() if exposure_attr else None)}")
        except Exception:
            log(f"{indent}{prim_type} 参数: <读取失败>")

    if prim.IsA(UsdGeom.Camera):
        try:
            focal_length = prim.GetAttribute("focalLength")
            h_aperture = prim.GetAttribute("horizontalAperture")
            v_aperture = prim.GetAttribute("verticalAperture")
            log(f"{indent}焦距: {format_value(focal_length.Get() if focal_length else None)}")
            log(f"{indent}水平孔径: {format_value(h_aperture.Get() if h_aperture else None)}")
            log(f"{indent}垂直孔径: {format_value(v_aperture.Get() if v_aperture else None)}")
        except Exception:
            log(f"{indent}Camera 参数: <读取失败>")


def describe_metadata(prim, indent):
    try:
        metadata = prim.GetAllAuthoredMetadata()
    except Exception:
        metadata = {}

    if not metadata:
        return

    log(f"{indent}Authored Metadata:")
    for key in sorted(metadata.keys()):
        log(f"{indent}  - {key}: {format_value(metadata[key])}")


def describe_attributes(prim, indent):
    try:
        attrs = sorted(prim.GetAttributes(), key=lambda x: x.GetName())
    except Exception:
        log(f"{indent}属性: <读取失败>")
        return

    useful_attrs = []
    for attr in attrs:
        try:
            authored = attr.HasAuthoredValue()
            connections = attr.GetConnections()
            if authored or connections:
                useful_attrs.append(attr)
        except Exception:
            continue

    if not useful_attrs:
        return

    log(f"{indent}已写入属性 ({len(useful_attrs)}):")
    for attr in useful_attrs:
        try:
            value = safe_get_attribute_value(attr)
            log(
                f"{indent}  - {attr.GetName()} [{attr.GetTypeName()}] = {format_value(value)}"
            )

            connections = attr.GetConnections()
            if connections:
                log(f"{indent}    连接: {[str(c) for c in connections]}")
        except Exception:
            log(f"{indent}  - {attr.GetName()}: <读取失败>")


def describe_relationships(prim, indent):
    try:
        relationships = sorted(prim.GetRelationships(), key=lambda x: x.GetName())
    except Exception:
        log(f"{indent}关系: <读取失败>")
        return

    useful_relationships = []
    for rel in relationships:
        try:
            targets = rel.GetTargets()
            if targets:
                useful_relationships.append((rel, targets))
        except Exception:
            continue

    if not useful_relationships:
        return

    log(f"{indent}关系 ({len(useful_relationships)}):")
    for rel, targets in useful_relationships:
        log(f"{indent}  - {rel.GetName()} -> {[str(t) for t in targets]}")


def describe_prim(prim, depth, xform_cache, bbox_cache):
    indent = "  " * depth
    log(f"{indent}{'-' * 80}")
    log(f"{indent}Prim: {prim.GetPath()}")
    log(f"{indent}名称: {prim.GetName()}")
    log(f"{indent}类型: {prim.GetTypeName() or '<无类型>'}")
    log(f"{indent}Active={prim.IsActive()} | Loaded={prim.IsLoaded()} | Defined={prim.IsDefined()}")
    log(f"{indent}Specifier={prim.GetSpecifier()} | Instance={prim.IsInstance()} | InstanceProxy={prim.IsInstanceProxy()}")

    try:
        kind = prim.GetMetadata("kind")
        if kind:
            log(f"{indent}Kind: {kind}")
    except Exception:
        pass

    describe_metadata(prim, indent)
    describe_xform(prim, indent, xform_cache)
    describe_bounds(prim, indent, bbox_cache)
    describe_material_binding(prim, indent)
    describe_physics_apis(prim, indent)
    describe_mesh(prim, indent)
    describe_light_or_camera(prim, indent)
    describe_attributes(prim, indent)
    describe_relationships(prim, indent)


def dump_tree(prim, depth, xform_cache, bbox_cache):
    describe_prim(prim, depth, xform_cache, bbox_cache)
    for child in prim.GetChildren():
        dump_tree(child, depth + 1, xform_cache, bbox_cache)


def summarize_stage(stage):
    all_prims = list(stage.Traverse())
    type_counts = {}

    mesh_paths = []
    material_paths = []
    light_paths = []
    camera_paths = []
    physics_paths = []

    for prim in all_prims:
        prim_type = prim.GetTypeName() or "<无类型>"
        type_counts[prim_type] = type_counts.get(prim_type, 0) + 1

        if prim_type == "Mesh":
            mesh_paths.append(str(prim.GetPath()))
        if prim_type == "Material":
            material_paths.append(str(prim.GetPath()))
        if is_light_prim(prim):
            light_paths.append(str(prim.GetPath()))
        if prim.IsA(UsdGeom.Camera):
            camera_paths.append(str(prim.GetPath()))

        has_physics = False
        try:
            has_physics = (
                prim.HasAPI(UsdPhysics.RigidBodyAPI)
                or prim.HasAPI(UsdPhysics.CollisionAPI)
                or prim.HasAPI(UsdPhysics.MassAPI)
            )
        except Exception:
            has_physics = False
        if has_physics:
            physics_paths.append(str(prim.GetPath()))

    log("=" * 100)
    log("Stage 基础信息")
    log("=" * 100)
    log(f"Root Layer Identifier: {stage.GetRootLayer().identifier}")
    log(f"Root Layer Real Path: {stage.GetRootLayer().realPath}")
    log(f"Session Layer Identifier: {stage.GetSessionLayer().identifier}")
    log(f"Default Prim: {format_value(stage.GetDefaultPrim().GetPath() if stage.GetDefaultPrim() else None)}")
    log(f"总 Prim 数量: {len(all_prims)}")
    log(f"Root 直接子节点数量: {len(stage.GetPseudoRoot().GetChildren())}")

    sub_layers = stage.GetRootLayer().subLayerPaths
    log(f"Root Layer 子层数量: {len(sub_layers)}")
    for sub_layer in sub_layers:
        log(f"  - {sub_layer}")

    log("\nPrim 类型统计:")
    for prim_type, count in sorted(type_counts.items(), key=lambda item: (-item[1], item[0])):
        log(f"  - {prim_type}: {count}")

    log("\nMesh 列表:")
    if mesh_paths:
        for path in mesh_paths:
            log(f"  - {path}")
    else:
        log("  - <无>")

    log("\nMaterial 列表:")
    if material_paths:
        for path in material_paths:
            log(f"  - {path}")
    else:
        log("  - <无>")

    log("\nLight 列表:")
    if light_paths:
        for path in light_paths:
            log(f"  - {path}")
    else:
        log("  - <无>")

    log("\nCamera 列表:")
    if camera_paths:
        for path in camera_paths:
            log(f"  - {path}")
    else:
        log("  - <无>")

    log("\n带物理 API 的 Prim:")
    if physics_paths:
        for path in physics_paths:
            log(f"  - {path}")
    else:
        log("  - <无>")


reset_output()

log("=" * 100)
log("Omniverse / Isaac Sim Stage 全量诊断开始")
log("=" * 100)
log(f"输出文件: {OUTPUT_FILE}")

try:
    stage = omni.usd.get_context().get_stage()

    if not stage:
        raise RuntimeError("没有打开的 Stage")

    summarize_stage(stage)

    xform_cache = UsdGeom.XformCache(Usd.TimeCode.Default())
    bbox_cache = UsdGeom.BBoxCache(
        Usd.TimeCode.Default(),
        [UsdGeom.Tokens.default_, UsdGeom.Tokens.render, UsdGeom.Tokens.proxy],
        useExtentsHint=True,
        ignoreVisibility=False,
    )

    log("\n" + "=" * 100)
    log("完整层级遍历")
    log("=" * 100)

    for prim in stage.GetPseudoRoot().GetChildren():
        dump_tree(prim, 0, xform_cache, bbox_cache)

    log("\n" + "=" * 100)
    log("Stage 全量诊断完成")
    log("=" * 100)

except Exception as e:
    log("\n" + "=" * 100)
    log("Stage 全量诊断失败")
    log("=" * 100)
    log(f"错误: {e}")
    log(traceback.format_exc())

log(f"诊断输出已保存到: {OUTPUT_FILE}")
