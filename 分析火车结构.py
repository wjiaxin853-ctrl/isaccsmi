from pxr import Usd, UsdPhysics, UsdGeom, Gf
import omni.usd
import datetime

# ==================================================
# 配置输出文件路径（请修改为你想要保存的位置）
# ==================================================
OUTPUT_FILE = "C:/Users/522/Desktop/train_diagnostic.txt"  # ⚠️ 可以修改这个路径


# 如果你想要其他位置，可以用这些示例：
# OUTPUT_FILE = "C:/temp/train_info.txt"
# OUTPUT_FILE = "D:/my_scripts/train_output.txt"
# OUTPUT_FILE = "./train_diagnostic.txt"  # 相对路径

# ==================================================
# 重定向print输出到文件和控制台
# ==================================================
class Tee:
    """同时输出到文件和控制台"""

    def __init__(self, file_path):
        self.file = open(file_path, 'w', encoding='utf-8')
        self.console = sys.stdout

    def write(self, message):
        self.console.write(message)
        self.file.write(message)
        self.file.flush()

    def flush(self):
        self.console.flush()
        self.file.flush()


import sys

sys.stdout = Tee(OUTPUT_FILE)

# 获取当前Stage
stage = omni.usd.get_context().get_stage()


def analyze_prim(prim, depth=0, max_depth=5):
    """递归分析prim的结构"""
    if depth > max_depth:
        return

    indent = "  " * depth

    # 获取prim的基本信息
    prim_name = prim.GetName()
    prim_path = prim.GetPath()
    prim_type = prim.GetTypeName()

    # 检查是否有物理属性
    has_rigidbody = False
    has_collision = False
    has_mass = False

    try:
        rigidbody_api = UsdPhysics.RigidBodyAPI.Get(prim)
        has_rigidbody = rigidbody_api is not None
    except:
        pass

    try:
        collision_api = UsdPhysics.CollisionAPI.Get(prim)
        has_collision = collision_api is not None
    except:
        pass

    try:
        mass_api = UsdPhysics.MassAPI.Get(prim)
        has_mass = mass_api is not None
    except:
        pass

    # 标记物理属性
    physics_tags = []
    if has_rigidbody:
        physics_tags.append("🔴刚体")
    if has_collision:
        physics_tags.append("🟢碰撞体")
    if has_mass:
        physics_tags.append("⚪质量")

    physics_str = f" [{', '.join(physics_tags)}]" if physics_tags else ""

    # 打印信息
    print(f"{indent}📦 {prim_name} (类型: {prim_type}){physics_str}")
    print(f"{indent}   路径: {prim_path}")

    # 如果是几何体，打印网格信息
    if prim_type == "Mesh":
        try:
            mesh = UsdGeom.Mesh(prim)
            points_attr = mesh.GetPointsAttr()
            if points_attr and points_attr.Get():
                point_count = len(points_attr.Get())
                print(f"{indent}   - 顶点数: {point_count}")
        except:
            pass

    # 递归分析子物体
    for child in prim.GetChildren():
        analyze_prim(child, depth + 1, max_depth)


def find_physics_components(prim, physics_items=None):
    """查找所有有物理组件的prim"""
    if physics_items is None:
        physics_items = []

    has_rigidbody = False
    has_collision = False

    try:
        rigidbody_api = UsdPhysics.RigidBodyAPI.Get(prim)
        has_rigidbody = rigidbody_api is not None
    except:
        pass

    try:
        collision_api = UsdPhysics.CollisionAPI.Get(prim)
        has_collision = collision_api is not None
    except:
        pass

    if has_rigidbody or has_collision:
        physics_items.append({
            "name": prim.GetName(),
            "path": str(prim.GetPath()),
            "rigidbody": has_rigidbody,
            "collision": has_collision
        })

    for child in prim.GetChildren():
        find_physics_components(child, physics_items)

    return physics_items


def count_prims_by_type(prim, type_counts=None):
    """统计各类型prim的数量"""
    if type_counts is None:
        type_counts = {}

    prim_type = prim.GetTypeName()
    type_counts[prim_type] = type_counts.get(prim_type, 0) + 1

    for child in prim.GetChildren():
        count_prims_by_type(child, type_counts)

    return type_counts


# ==================================================
# 主程序
# ==================================================

print("=" * 60)
print("🚂 火车模型诊断报告")
print(f"生成时间: {datetime.datetime.now()}")
print("=" * 60)

# 1. 首先查看/root下的所有内容
root_prim = stage.GetPrimAtPath("/root")

if not root_prim:
    print("❌ 找不到 /root 节点！")
    print("正在查找场景根节点...")

    # 列出所有根节点
    root_prims = stage.GetRootLayer().GetRootPrims()
    if root_prims:
        print(f"✅ 找到 {len(root_prims)} 个根节点:")
        for prim in root_prims:
            print(f"   - {prim.GetPath()}")
        # 使用第一个找到的根节点
        root_prim = root_prims[0]
    else:
        print("❌ 场景中没有任何物体！")
        exit()

print(f"\n📁 正在分析: {root_prim.GetPath()}")
print(f"物体名称: {root_prim.GetName()}")
print(f"物体类型: {root_prim.GetTypeName()}")
print()

# 2. 打印完整的层级结构
print("=" * 60)
print("📋 完整层级结构:")
print("=" * 60)
analyze_prim(root_prim)

# 3. 查找所有有物理组件的物体
print("\n" + "=" * 60)
print("🔧 已存在的物理组件:")
print("=" * 60)
physics_items = find_physics_components(root_prim)

if physics_items:
    for item in physics_items:
        rb_mark = "✓" if item["rigidbody"] else "✗"
        col_mark = "✓" if item["collision"] else "✗"
        print(f"📦 {item['name']}")
        print(f"   路径: {item['path']}")
        print(f"   刚体: {rb_mark} | 碰撞体: {col_mark}")
else:
    print("⚠️ 未找到任何物理组件（刚体/碰撞体）")

# 4. 统计所有物体类型
print("\n" + "=" * 60)
print("📊 物体类型统计:")
print("=" * 60)
type_counts = count_prims_by_type(root_prim)
for prim_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
    print(f"   {prim_type}: {count} 个")

# 5. 生成建议的部件列表
print("\n" + "=" * 60)
print("💡 建议的火车部件列表（可直接复制使用）:")
print("=" * 60)


def generate_parts_list(prim, parts_list=None):
    """生成所有部件的路径列表"""
    if parts_list is None:
        parts_list = []

    # 添加这个prim（如果是Mesh或Xform）
    prim_type = prim.GetTypeName()
    if prim_type in ["Mesh", "Xform", "Scope", "Group"]:
        parts_list.append(str(prim.GetPath()))

    for child in prim.GetChildren():
        generate_parts_list(child, parts_list)

    return parts_list


all_parts = generate_parts_list(root_prim)

print("\n# 复制以下内容到你的代码中：")
print("train_parts = [")
for i, part in enumerate(all_parts):
    if i < len(all_parts) - 1:
        print(f'    "{part}",')
    else:
        print(f'    "{part}"')
print("]")

# 6. 简单判断火车结构
print("\n" + "=" * 60)
print("🎯 结构分析:")
print("=" * 60)

mesh_count = type_counts.get("Mesh", 0)
xform_count = type_counts.get("Xform", 0)

print(f"📐 网格数量: {mesh_count}")
print(f"📁 变换节点数量: {xform_count}")

if mesh_count > 5:
    print("⚠️ 你的火车由多个独立网格组成，需要整合为单个刚体")
    print("💡 建议：使用方案一（所有部件合并为一个刚体）")
else:
    print("✅ 火车结构相对简单，容易处理")

print("\n" + "=" * 60)
print(f"✅ 诊断完成！报告已保存到: {OUTPUT_FILE}")
print("=" * 60)

# 恢复标准输出并关闭文件
sys.stdout.file.close()
sys.stdout = sys.stdout.console

print(f"\n📄 报告已保存到: {OUTPUT_FILE}")
print("请打开这个文件并把内容复制给我")