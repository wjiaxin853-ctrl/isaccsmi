import io
import os
import re
import sys
import traceback

import omni.usd
from pxr import Gf, Sdf, UsdShade


DEFAULT_OUTPUT_DIR = r"C:\Users\522\Desktop\code\isaccsmi"
DEFAULT_TEXTURE_DIR = r"C:\Users\522\Downloads\1238088_07711214bf3dcb13d3b8e9ac84b3231f"
DEFAULT_TARGET_MESH_PATH = "/World/Obj3d66_1238088_1_934"
DEFAULT_LOOKS_SCOPE_PATH = "/World/Obj3d66_1238088_1_934_Looks"

# 如果你已经知道材质分区和贴图编号的对应关系，可以直接在这里手工指定。
# 当前采用试验映射 C：
# 保留上一版明显更好的前 7 个分区，只替换最后 2 个分区继续试。
MANUAL_TEXTURE_MAP = {
    1: 1,
    2: 2,
    3: 10,
    4: 11,
    5: 12,
    6: 13,
    7: 14,
    8: 17,
    9: 18,
}

OUTPUT_DIR = os.environ.get("OBJ3D66_BIND_OUTPUT_DIR", DEFAULT_OUTPUT_DIR)
TEXTURE_DIR = os.environ.get("OBJ3D66_TEXTURE_DIR", DEFAULT_TEXTURE_DIR)
TARGET_MESH_PATH = os.environ.get("OBJ3D66_TARGET_MESH_PATH", DEFAULT_TARGET_MESH_PATH)
LOOKS_SCOPE_PATH = os.environ.get("OBJ3D66_LOOKS_SCOPE_PATH", DEFAULT_LOOKS_SCOPE_PATH)

MODEL_HINT_TOKENS = [
    "1238088",
    "obj3d66",
    "3d66model",
]

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".tga", ".exr"}
ROLE_PRIORITY = ("diffuse", "normal", "roughness", "opacity", "metallic", "unknown")
ROLE_KEYWORDS = {
    "diffuse": [
        "basecolor",
        "base_color",
        "basecolour",
        "base_colour",
        "albedo",
        "diffuse",
        "diff",
        "color",
        "colour",
        "col",
    ],
    "normal": [
        "normalmap",
        "normal",
        "nrm",
        "nor",
    ],
    "roughness": [
        "reflectionroughness",
        "reflection_roughness",
        "roughness",
        "rough",
        "glossiness",
        "gloss",
    ],
    "opacity": [
        "opacitymask",
        "opacity",
        "transparent",
        "transparency",
        "alpha",
        "mask",
    ],
    "metallic": [
        "metalness",
        "metallic",
        "metal",
    ],
}


def log(message):
    print(str(message))


def normalize_text(value):
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def extract_small_numbers(value):
    numbers = []
    for match in re.findall(r"(?<!\d)(\d{1,3})(?!\d)", value):
        number = int(match)
        if 0 < number <= 99:
            numbers.append(number)
    return sorted(set(numbers))


def extract_file_sequence(file_name):
    match = re.search(r"files-(\d+)(?:\.[^.]+)?$", file_name.lower())
    if match:
        return int(match.group(1))
    return None


def detect_role(file_stem):
    normalized = normalize_text(file_stem)

    for role in ("normal", "roughness", "opacity", "metallic", "diffuse"):
        for keyword in ROLE_KEYWORDS[role]:
            if keyword in normalized.replace(" ", "") or keyword in normalized:
                return role

    return "unknown"


def remove_role_tokens(file_stem):
    value = file_stem.lower()
    for keywords in ROLE_KEYWORDS.values():
        for keyword in sorted(keywords, key=len, reverse=True):
            value = value.replace(keyword, " ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def score_texture_entry(entry):
    name = entry["name_lower"]
    path_lower = entry["path"].lower()

    score = 0
    for token in MODEL_HINT_TOKENS:
        if token in name:
            score += 6
        if token in path_lower:
            score += 3

    if entry["role"] != "unknown":
        score += 2

    if entry["mat_ids"]:
        score += 1

    return score


def scan_texture_files(texture_dir):
    entries = []

    for root, _, files in os.walk(texture_dir):
        for file_name in files:
            extension = os.path.splitext(file_name)[1].lower()
            if extension not in SUPPORTED_EXTENSIONS:
                continue

            stem = os.path.splitext(file_name)[0]
            role = detect_role(stem)
            file_index = extract_file_sequence(file_name)
            mat_ids = [file_index] if file_index is not None else extract_small_numbers(stem)
            group_key = remove_role_tokens(stem)

            entry = {
                "path": os.path.join(root, file_name),
                "file_name": file_name,
                "name_lower": file_name.lower(),
                "stem": stem,
                "role": role,
                "mat_ids": mat_ids,
                "file_index": file_index,
                "group_key": group_key,
            }
            entry["score"] = score_texture_entry(entry)
            entries.append(entry)

    entries.sort(
        key=lambda item: (
            -item["score"],
            item["file_index"] if item["file_index"] is not None else 10**9,
            item["file_name"].lower(),
        )
    )
    return entries


def filter_relevant_textures(entries):
    filtered = []
    for entry in entries:
        if any(token in entry["name_lower"] for token in MODEL_HINT_TOKENS):
            filtered.append(entry)

    if filtered:
        return filtered

    return entries


def classify_textures(entries):
    grouped = {role: [] for role in ROLE_PRIORITY}
    for entry in entries:
        grouped.setdefault(entry["role"], []).append(entry)

    if not grouped["diffuse"] and grouped["unknown"]:
        grouped["diffuse"] = list(grouped["unknown"])

    for role in grouped:
        grouped[role].sort(
            key=lambda item: (
                -item["score"],
                item["file_index"] if item["file_index"] is not None else 10**9,
                item["file_name"].lower(),
            )
        )

    return grouped


def pick_best_texture(entries, mat_id):
    if not entries:
        return None

    exact_matches = [entry for entry in entries if mat_id in entry["mat_ids"]]
    if exact_matches:
        exact_matches.sort(
            key=lambda item: (
                -item["score"],
                item["file_index"] if item["file_index"] is not None else 10**9,
                item["file_name"].lower(),
            )
        )
        return exact_matches[0]

    if len(entries) == 1:
        return entries[0]

    near_matches = []
    for entry in entries:
        if entry["mat_ids"]:
            distance = min(abs(number - mat_id) for number in entry["mat_ids"])
            near_matches.append(
                (
                    distance,
                    -entry["score"],
                    entry["file_index"] if entry["file_index"] is not None else 10**9,
                    entry["file_name"].lower(),
                    entry,
                )
            )

    near_matches.sort()
    if near_matches and near_matches[0][0] <= 1:
        return near_matches[0][4]

    sorted_by_id = [entry for entry in entries if entry["mat_ids"]]
    sorted_by_id.sort(
        key=lambda item: (
            min(item["mat_ids"]) if item["mat_ids"] else 999,
            -item["score"],
            item["file_index"] if item["file_index"] is not None else 10**9,
            item["file_name"].lower(),
        )
    )

    if len(sorted_by_id) >= mat_id:
        return sorted_by_id[mat_id - 1]

    return entries[0]


def get_subset_mat_id(subset_prim):
    try:
        custom_data = subset_prim.GetCustomData()
        mat_id = custom_data.get("3dsmax", {}).get("matId")
        if mat_id:
            return int(mat_id)
    except Exception:
        pass

    match = re.search(r"_(\d+)_", subset_prim.GetName())
    if match:
        return int(match.group(1))

    return None


def define_scope(stage, scope_path):
    scope_prim = stage.GetPrimAtPath(scope_path)
    if not scope_prim:
        scope_prim = stage.DefinePrim(scope_path, "Scope")
    return scope_prim


def ensure_shader_source(shader):
    try:
        shader.CreateImplementationSourceAttr(UsdShade.Tokens.sourceAsset)
    except Exception:
        shader.GetPrim().CreateAttribute(
            "info:implementationSource",
            Sdf.ValueTypeNames.Token,
        ).Set("sourceAsset")

    try:
        shader.SetSourceAsset(Sdf.AssetPath("OmniPBR.mdl"), "mdl")
    except Exception:
        shader.GetPrim().CreateAttribute(
            "info:mdl:sourceAsset",
            Sdf.ValueTypeNames.Asset,
        ).Set(Sdf.AssetPath("OmniPBR.mdl"))

    try:
        shader.SetSourceAssetSubIdentifier("OmniPBR", "mdl")
    except Exception:
        shader.GetPrim().CreateAttribute(
            "info:mdl:sourceAsset:subIdentifier",
            Sdf.ValueTypeNames.Token,
        ).Set("OmniPBR")


def set_shader_input(shader, name, value_type, value):
    shader.CreateInput(name, value_type).Set(value)


def asset_path(texture_file):
    return Sdf.AssetPath(texture_file.replace("\\", "/"))


def create_omnipbr_material(stage, material_path, shader_name, texture_map):
    material = UsdShade.Material.Define(stage, material_path)
    shader = UsdShade.Shader.Define(stage, f"{material_path}/{shader_name}")

    ensure_shader_source(shader)
    shader_out = shader.CreateOutput("out", Sdf.ValueTypeNames.Token)

    material.CreateSurfaceOutput("mdl").ConnectToSource(shader.ConnectableAPI(), "out")

    try:
        material.CreateVolumeOutput("mdl").ConnectToSource(shader.ConnectableAPI(), "out")
        material.CreateDisplacementOutput("mdl").ConnectToSource(shader.ConnectableAPI(), "out")
    except Exception:
        pass

    set_shader_input(
        shader,
        "diffuse_color_constant",
        Sdf.ValueTypeNames.Color3f,
        Gf.Vec3f(0.5, 0.5, 0.5),
    )
    set_shader_input(
        shader,
        "emissive_color",
        Sdf.ValueTypeNames.Color3f,
        Gf.Vec3f(1.0, 1.0, 1.0),
    )
    set_shader_input(shader, "emissive_intensity", Sdf.ValueTypeNames.Float, 10000.0)
    set_shader_input(shader, "enable_emission", Sdf.ValueTypeNames.Bool, False)
    set_shader_input(shader, "enable_opacity", Sdf.ValueTypeNames.Bool, True)
    set_shader_input(
        shader,
        "enable_opacity_texture",
        Sdf.ValueTypeNames.Bool,
        texture_map["opacity"] is not None,
    )
    set_shader_input(shader, "opacity_constant", Sdf.ValueTypeNames.Float, 1.0)
    set_shader_input(shader, "opacity_mode", Sdf.ValueTypeNames.Int, 1)
    set_shader_input(shader, "opacity_threshold", Sdf.ValueTypeNames.Float, 0.0)
    set_shader_input(
        shader,
        "reflection_roughness_texture_influence",
        Sdf.ValueTypeNames.Float,
        1.0 if texture_map["roughness"] else 0.0,
    )
    set_shader_input(shader, "texture_rotate", Sdf.ValueTypeNames.Float, 0.0)
    set_shader_input(
        shader,
        "texture_scale",
        Sdf.ValueTypeNames.Float2,
        Gf.Vec2f(1.0, 1.0),
    )
    set_shader_input(
        shader,
        "texture_translate",
        Sdf.ValueTypeNames.Float2,
        Gf.Vec2f(0.0, 0.0),
    )

    if texture_map["diffuse"]:
        set_shader_input(
            shader,
            "diffuse_texture",
            Sdf.ValueTypeNames.Asset,
            asset_path(texture_map["diffuse"]),
        )

    if texture_map["normal"]:
        set_shader_input(
            shader,
            "normalmap_texture",
            Sdf.ValueTypeNames.Asset,
            asset_path(texture_map["normal"]),
        )

    if texture_map["roughness"]:
        set_shader_input(
            shader,
            "reflectionroughness_texture",
            Sdf.ValueTypeNames.Asset,
            asset_path(texture_map["roughness"]),
        )

    if texture_map["opacity"]:
        set_shader_input(
            shader,
            "opacity_texture",
            Sdf.ValueTypeNames.Asset,
            asset_path(texture_map["opacity"]),
        )

    if texture_map["metallic"]:
        set_shader_input(
            shader,
            "metallic_texture",
            Sdf.ValueTypeNames.Asset,
            asset_path(texture_map["metallic"]),
        )
        set_shader_input(shader, "metallic_texture_influence", Sdf.ValueTypeNames.Float, 1.0)

    return material


def bind_material_to_prim(target_prim, material):
    binding_api = UsdShade.MaterialBindingAPI.Apply(target_prim)
    binding_api.Bind(material)


def summarize_texture_groups(grouped_textures):
    log("扫描到的贴图分类结果：")
    for role in ROLE_PRIORITY:
        entries = grouped_textures.get(role, [])
        log(f"  - {role}: {len(entries)} 个")
        for entry in entries[:12]:
            log(
                f"      {entry['file_name']} | file_index={entry['file_index']} | mat_ids={entry['mat_ids'] or '无'} | score={entry['score']}"
            )
        if len(entries) > 12:
            log(f"      ... 其余 {len(entries) - 12} 个省略")


def select_target_mesh(stage):
    target_prim = stage.GetPrimAtPath(TARGET_MESH_PATH)
    if target_prim:
        return target_prim

    for prim in stage.Traverse():
        if prim.GetTypeName() != "Mesh":
            continue
        if "obj3d66_1238088" in prim.GetName().lower():
            return prim

    return None


def choose_texture_map(grouped_textures, mat_id):
    return {
        "diffuse": (pick_best_texture(grouped_textures["diffuse"], mat_id) or {}).get("path"),
        "normal": (pick_best_texture(grouped_textures["normal"], mat_id) or {}).get("path"),
        "roughness": (pick_best_texture(grouped_textures["roughness"], mat_id) or {}).get("path"),
        "opacity": (pick_best_texture(grouped_textures["opacity"], mat_id) or {}).get("path"),
        "metallic": (pick_best_texture(grouped_textures["metallic"], mat_id) or {}).get("path"),
    }


def find_texture_by_file_index(entries, file_index):
    for entry in entries:
        if entry["file_index"] == file_index:
            return entry
    return None


def is_numbered_diffuse_pack(grouped_textures):
    diffuse_entries = grouped_textures.get("diffuse", [])
    if not diffuse_entries:
        return False

    if grouped_textures.get("normal") or grouped_textures.get("roughness") or grouped_textures.get("opacity") or grouped_textures.get("metallic"):
        return False

    return all(entry["file_index"] is not None for entry in diffuse_entries)


def build_manual_or_sequential_diffuse_map(subsets_with_ids, grouped_textures):
    assignments = {}
    diffuse_entries = grouped_textures.get("diffuse", [])

    if not diffuse_entries:
        return assignments

    if MANUAL_TEXTURE_MAP:
        log("")
        log(f"使用手工贴图映射: {MANUAL_TEXTURE_MAP}")
        for mat_id, _ in subsets_with_ids:
            file_index = MANUAL_TEXTURE_MAP.get(mat_id)
            if file_index is None:
                continue
            entry = find_texture_by_file_index(diffuse_entries, file_index)
            if entry:
                assignments[mat_id] = entry["path"]
            else:
                log(f"⚠️ 手工映射 matId={mat_id} -> files-{file_index}.png 未找到")
        return assignments

    if is_numbered_diffuse_pack(grouped_textures):
        sorted_entries = sorted(
            diffuse_entries,
            key=lambda item: (
                item["file_index"] if item["file_index"] is not None else 10**9,
                item["file_name"].lower(),
            ),
        )

        log("")
        log("检测到当前目录是一组纯编号 diffuse PNG，将按编号顺序依次分配给各个 matId。")
        preview = [entry["file_index"] for entry in sorted_entries[: min(20, len(sorted_entries))]]
        log(f"可用编号预览: {preview}")

        for index, (mat_id, _) in enumerate(subsets_with_ids):
            if index < len(sorted_entries):
                assignments[mat_id] = sorted_entries[index]["path"]

    return assignments


def material_name_for_subset(subset_name, mat_id):
    safe_subset_name = re.sub(r"[^A-Za-z0-9_]+", "_", subset_name).strip("_")
    return f"Obj3d66_1238088_mat_{mat_id:02d}_{safe_subset_name}"


os.makedirs(OUTPUT_DIR, exist_ok=True)

original_stdout = sys.stdout
sys.stdout = io.StringIO()

try:
    log("=" * 80)
    log("Obj3d66_1238088_1_934 自动贴图绑定")
    log("=" * 80)
    log(f"目标 Mesh: {TARGET_MESH_PATH}")
    log(f"贴图目录: {TEXTURE_DIR}")
    log(f"材质 Scope: {LOOKS_SCOPE_PATH}")

    stage = omni.usd.get_context().get_stage()
    if not stage:
        raise RuntimeError("没有打开的 Stage")

    if not os.path.isdir(TEXTURE_DIR):
        raise RuntimeError(f"贴图目录不存在: {TEXTURE_DIR}")

    target_mesh = select_target_mesh(stage)
    if not target_mesh:
        raise RuntimeError(f"找不到目标 Mesh: {TARGET_MESH_PATH}")

    log(f"实际绑定 Mesh: {target_mesh.GetPath()}")

    subsets = [child for child in target_mesh.GetChildren() if child.GetTypeName() == "GeomSubset"]
    if subsets:
        subsets_with_ids = []
        for subset in subsets:
            mat_id = get_subset_mat_id(subset)
            if mat_id is None:
                raise RuntimeError(f"无法识别 GeomSubset 的 matId: {subset.GetPath()}")
            subsets_with_ids.append((mat_id, subset))
        subsets_with_ids.sort(key=lambda item: item[0])
    else:
        subsets_with_ids = [(1, target_mesh)]

    log(f"待绑定分区数量: {len(subsets_with_ids)}")
    for mat_id, subset in subsets_with_ids:
        log(f"  - matId={mat_id} -> {subset.GetPath()}")

    all_textures = scan_texture_files(TEXTURE_DIR)
    if not all_textures:
        raise RuntimeError("贴图目录中没有找到支持的贴图文件")

    relevant_textures = filter_relevant_textures(all_textures)
    grouped_textures = classify_textures(relevant_textures)

    log("")
    summarize_texture_groups(grouped_textures)

    if not grouped_textures["diffuse"]:
        raise RuntimeError("没有识别到可用的 diffuse/basecolor/albedo 贴图")

    diffuse_assignments = build_manual_or_sequential_diffuse_map(subsets_with_ids, grouped_textures)

    define_scope(stage, LOOKS_SCOPE_PATH)

    success_count = 0
    for mat_id, subset in subsets_with_ids:
        texture_map = choose_texture_map(grouped_textures, mat_id)
        if mat_id in diffuse_assignments:
            texture_map["diffuse"] = diffuse_assignments[mat_id]

        if not texture_map["diffuse"]:
            log(f"⚠️ matId={mat_id} 没有匹配到 diffuse 贴图，跳过 {subset.GetPath()}")
            continue

        material_name = material_name_for_subset(subset.GetName(), mat_id)
        material_path = f"{LOOKS_SCOPE_PATH}/{material_name}"

        log("")
        log(f"开始处理 matId={mat_id} | {subset.GetPath()}")
        log(f"  材质路径: {material_path}")
        log(f"  diffuse : {texture_map['diffuse']}")
        log(f"  normal  : {texture_map['normal'] or '未匹配'}")
        log(f"  roughness/glossiness: {texture_map['roughness'] or '未匹配'}")
        log(f"  opacity : {texture_map['opacity'] or '未匹配'}")
        log(f"  metallic: {texture_map['metallic'] or '未匹配'}")

        material = create_omnipbr_material(stage, material_path, material_name, texture_map)
        bind_material_to_prim(subset, material)
        success_count += 1
        log("  ✅ 已完成材质创建并绑定")

    log("")
    log("=" * 80)
    log(f"完成：成功绑定 {success_count} 个分区")
    log("提示：如果场景里效果正确，再手动保存当前 Stage。")
    log("=" * 80)

except Exception as exc:
    log("")
    log("=" * 80)
    log("脚本执行失败")
    log("=" * 80)
    log(f"错误: {exc}")
    log(traceback.format_exc())

output_content = sys.stdout.getvalue()
sys.stdout = original_stdout

output_path = os.path.join(OUTPUT_DIR, "output.txt")
with open(output_path, "w", encoding="utf-8") as output_file:
    output_file.write(output_content)

print(f"输出已保存到: {output_path}")
