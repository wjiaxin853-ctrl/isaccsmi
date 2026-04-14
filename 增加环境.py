from pxr import Usd, UsdGeom, UsdPhysics, UsdShade, Gf
import omni.usd

# 获取当前Stage
stage = omni.usd.get_context().get_stage()

print("=" * 60)
print("🌍 正在为火车添加环境...")
print("=" * 60)


# ==================================================
# 1. 创建地面（带碰撞体）
# ==================================================
def create_ground():
    ground_path = "/World/Ground"
    ground_prim = stage.GetPrimAtPath(ground_path)

    if not ground_prim:
        # 创建一个大平面作为地面
        ground_prim = stage.DefinePrim(ground_path, "Mesh")
        ground_mesh = UsdGeom.Mesh(ground_prim)

        # 创建一个简单的平面网格（100x100）
        vertices = [
            (-50, -0.1, -50), (50, -0.1, -50),
            (50, -0.1, 50), (-50, -0.1, 50)
        ]
        face_indices = [0, 1, 2, 0, 2, 3]

        ground_mesh.CreatePointsAttr().Set(vertices)
        ground_mesh.CreateFaceVertexIndicesAttr().Set(face_indices)
        ground_mesh.CreateFaceVertexCountsAttr().Set([3, 3])

        # 添加碰撞体
        UsdPhysics.CollisionAPI.Apply(ground_prim)

        print("   ✅ 创建地面 (100x100)")
    else:
        print("   ✅ 地面已存在")

    return ground_prim


# ==================================================
# 2. 创建简单的参照标记
# ==================================================
def create_simple_markers():
    """创建简单的参照标记"""

    # 创建几个简单的标记点
    positions = [
        (-10, 0, -20), (-10, 0, -10), (-10, 0, 0), (-10, 0, 10), (-10, 0, 20),
        (10, 0, -20), (10, 0, -10), (10, 0, 0), (10, 0, 10), (10, 0, 20),
        (0, 0, -20), (0, 0, -10), (0, 0, 0), (0, 0, 10), (0, 0, 20)
    ]

    count = 0
    for i, pos in enumerate(positions):
        # 使用有效的路径名
        marker_path = f"/World/Marker_{i}"
        if not stage.GetPrimAtPath(marker_path):
            marker_prim = stage.DefinePrim(marker_path, "Cube")
            cube = UsdGeom.Cube(marker_prim)
            cube.CreateSizeAttr().Set(0.2)

            # 设置位置
            xform = UsdGeom.XformCommonAPI(marker_prim)
            xform.SetTranslate(Gf.Vec3d(pos[0], pos[1] + 0.1, pos[2]))
            count += 1

    print(f"   ✅ 创建 {count} 个参照标记")


# ==================================================
# 3. 创建环境光
# ==================================================
def create_lighting():
    """创建照明系统"""

    # 主光源（方向光）
    main_light_path = "/World/MainLight"
    main_light_prim = stage.GetPrimAtPath(main_light_path)

    if not main_light_prim:
        main_light_prim = stage.DefinePrim(main_light_path, "DistantLight")
        print(f"   ✅ 创建主光源")

    from pxr import UsdLux
    main_light = UsdLux.DistantLight(main_light_prim)
    main_light.CreateIntensityAttr().Set(3000)

    # 环境光
    env_light_path = "/World/EnvLight"
    env_light_prim = stage.GetPrimAtPath(env_light_path)

    if not env_light_prim:
        env_light_prim = stage.DefinePrim(env_light_path, "DomeLight")
        env_light = UsdLux.DomeLight(env_light_prim)
        env_light.CreateIntensityAttr().Set(300)
        print(f"   ✅ 创建环境光")

    print("   💡 照明系统设置完成")


# ==================================================
# 4. 创建参照柱（沿Z轴）
# ==================================================
def create_pillars():
    """创建简单的参照柱"""

    # 沿Z轴创建柱子
    count = 0
    for z in range(-30, 35, 5):
        # 使用有效的路径名 - 处理负数
        z_str = str(z).replace('-', 'n')
        pillar_path = f"/World/Pillar_z{z_str}"

        if not stage.GetPrimAtPath(pillar_path):
            pillar_prim = stage.DefinePrim(pillar_path, "Cylinder")
            cylinder = UsdGeom.Cylinder(pillar_prim)
            cylinder.CreateHeightAttr().Set(1.0)
            cylinder.CreateRadiusAttr().Set(0.15)

            # 放置到轨道两侧
            xform = UsdGeom.XformCommonAPI(pillar_prim)
            xform.SetTranslate(Gf.Vec3d(2.5, 0.5, float(z)))
            count += 1

            # 同时创建左侧的柱子
            left_path = f"/World/Pillar_z{z_str}_left"
            if not stage.GetPrimAtPath(left_path):
                left_prim = stage.DefinePrim(left_path, "Cylinder")
                left_cylinder = UsdGeom.Cylinder(left_prim)
                left_cylinder.CreateHeightAttr().Set(1.0)
                left_cylinder.CreateRadiusAttr().Set(0.15)
                left_xform = UsdGeom.XformCommonAPI(left_prim)
                left_xform.SetTranslate(Gf.Vec3d(-2.5, 0.5, float(z)))
                count += 1

    print(f"   ✅ 创建 {count} 个参照柱")


# ==================================================
# 5. 确保物理场景存在
# ==================================================
def ensure_physics_scene():
    """确保物理场景已设置"""
    scene_path = "/World/physicsScene"
    scene_prim = stage.GetPrimAtPath(scene_path)

    if not scene_prim:
        scene_prim = stage.DefinePrim(scene_path, "UsdPhysicsScene")
        physics_scene = UsdPhysics.Scene(scene_prim)
        physics_scene.CreateGravityDirectionAttr().Set(Gf.Vec3f(0, -1, 0))
        physics_scene.CreateGravityMagnitudeAttr().Set(9.8)
        print("   ✅ 创建物理场景")
    else:
        print("   ✅ 物理场景已存在")


# ==================================================
# 6. 创建地面网格线（辅助观察）
# ==================================================
def create_ground_grid():
    """创建地面网格线"""

    count = 0
    step = 5
    for x in range(-25, 26, step):
        for z in range(-25, 26, step):
            if x == 0 and z == 0:
                continue
            # 使用安全的路径名
            x_str = str(x).replace('-', 'n')
            z_str = str(z).replace('-', 'n')
            grid_path = f"/World/Grid_{x_str}_{z_str}"

            if not stage.GetPrimAtPath(grid_path):
                grid_prim = stage.DefinePrim(grid_path, "Cube")
                cube = UsdGeom.Cube(grid_prim)
                cube.CreateSizeAttr().Set(0.1)

                xform = UsdGeom.XformCommonAPI(grid_prim)
                xform.SetTranslate(Gf.Vec3d(float(x), 0.05, float(z)))
                count += 1

    print(f"   ✅ 创建 {count} 个网格辅助点")


# ==================================================
# 执行所有环境设置
# ==================================================

# 确保物理场景存在
ensure_physics_scene()

# 创建地面
create_ground()

# 创建参照标记
create_simple_markers()

# 创建照明
create_lighting()

# 创建参照柱
create_pillars()

# 创建网格辅助点
create_ground_grid()

print("\n" + "=" * 60)
print("✅ 环境添加完成！")
print("=" * 60)
print("📌 现在场景包含：")
print("   - 地面 (100x100，带碰撞体)")
print("   - 参照标记点（小立方体）")
print("   - 轨道沿线参照柱（左右两侧）")
print("   - 主光源 + 环境光")
print("   - 网格辅助点")
print("\n💡 提示：")
print("   - 参照物可以帮助观察火车移动")
print("   - 火车移动时，参照物会向后移动")
print("   - 按 'Ctrl+Shift+F' 重置相机")
print("   - 按 'Alt+鼠标左键' 旋转视角")
print("=" * 60)