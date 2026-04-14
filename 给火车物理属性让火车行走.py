from pxr import Usd, UsdPhysics, UsdGeom, Gf
import omni.usd

# 获取当前Stage
stage = omni.usd.get_context().get_stage()


# ==================================================
# 1. 设置物理场景和重力
# ==================================================
def setup_physics_scene(stage):
    """设置物理场景和重力"""
    scene_path = "/World/physicsScene"
    scene_prim = stage.GetPrimAtPath(scene_path)

    if not scene_prim:
        scene_prim = stage.DefinePrim(scene_path, "UsdPhysicsScene")
        print(f"✅ 已创建物理场景节点: {scene_path}")

    physics_scene = UsdPhysics.Scene(scene_prim)
    gravity_dir_attr = physics_scene.CreateGravityDirectionAttr()
    gravity_dir_attr.Set(Gf.Vec3f(0, -1, 0))
    gravity_mag_attr = physics_scene.CreateGravityMagnitudeAttr()
    gravity_mag_attr.Set(9.8)

    print(f"⚙️ 重力设置完成")
    return physics_scene


# ==================================================
# 2. 获取物体的包围盒
# ==================================================
def get_prim_bounds(prim):
    """获取物体的包围盒（最小和最大点）"""
    # 获取物体在世界坐标系中的边界
    boundable = UsdGeom.Boundable(prim)
    time_code = Usd.TimeCode.Default()
    bounds = boundable.ComputeWorldBound(time_code, UsdGeom.Tokens.default_)
    range = bounds.ComputeAlignedRange()
    return range.GetMin(), range.GetMax()


# ==================================================
# 3. 为物体创建简单的盒子碰撞体
# ==================================================
def add_box_collider(prim, size=None):
    """为物体添加盒子碰撞体"""
    if not size:
        # 自动计算包围盒大小
        min_point, max_point = get_prim_bounds(prim)
        size = (max_point[0] - min_point[0],
                max_point[1] - min_point[1],
                max_point[2] - min_point[2])
        center = ((min_point[0] + max_point[0]) / 2,
                  (min_point[1] + max_point[1]) / 2,
                  (min_point[2] + max_point[2]) / 2)
    else:
        center = (0, 0, 0)

    # 创建碰撞体prim
    collider_path = str(prim.GetPath()) + "_collider"
    collider_prim = stage.DefinePrim(collider_path, "PhysicsCube")

    # 设置碰撞体大小
    cube = UsdGeom.Cube(collider_prim)
    cube.CreateSizeAttr().Set(size[0])  # 假设使用X轴长度
    # 注意：实际需要根据三个轴分别设置，这里简化处理

    # 设置碰撞体的变换
    xform = UsdGeom.XformCommonAPI(collider_prim)
    xform.SetTranslate((center[0], center[1], center[2]))

    # 添加碰撞体API
    collision_api = UsdPhysics.CollisionAPI.Apply(collider_prim)

    # 将碰撞体绑定到原始物体
    rigid_body_api = UsdPhysics.RigidBodyAPI.Get(prim)
    if rigid_body_api:
        # 设置碰撞体为刚体的子物体
        pass

    print(f"   📦 添加盒子碰撞体: 大小 {size}")
    return collider_prim


# ==================================================
# 4. 简化版：直接为主部件添加刚体，忽略子部件碰撞
# ==================================================
def make_train_rigid_body_simple(stage):
    """简化版：只为主部件添加刚体和简单碰撞体"""

    # 火车部件路径
    train_mesh_parts = [
        "/root/Obj3d66_1238088_2_970",
        "/root/Obj3d66_1238088_3_500",
        "/root/Obj3d66_1238088_4_286",
        "/root/Obj3d66_1238088_5_854",
        "/root/Obj3d66_1238088_6_606",
        "/root/Obj3d66_1238088_7_531",
        "/root/Obj3d66_1238088_8_943",
        "/root/Obj3d66_1238088_9_63",
        "/root/Obj3d66_1238088_10_133",
        "/root/Obj3d66_1238088_11_215",
        "/root/Obj3d66_1238088_12_251",
        "/root/Obj3d66_1238088_13_751",
        "/root/Obj3d66_1238088_14_529",
        "/root/Obj3d66_1238088_15_333",
        "/root/Obj3d66_1238088_16_608",
        "/root/Obj3d66_1238088_17_880",
        "/root/Obj3d66_1238088_18_338",
        "/root/Obj3d66_1238088_19_874",
        "/root/Obj3d66_1238088_20_433",
        "/root/Obj3d66_1238088_21_947",
    ]

    # 选择主部件（最大的那个）
    main_part_path = "/root/Obj3d66_1238088_17_880"  # 顶点数最多，应该是车身
    main_prim = stage.GetPrimAtPath(main_part_path)

    if not main_prim:
        print(f"❌ 找不到主部件")
        return None

    print(f"🚂 简化方案：只为主部件添加物理效果")
    print(f"   主部件: {main_part_path}")

    # 添加刚体
    rigid_body_api = UsdPhysics.RigidBodyAPI.Apply(main_prim)
    rigid_body_api.CreateStartsAsleepAttr().Set(False)

    # 添加质量
    mass_api = UsdPhysics.MassAPI.Apply(main_prim)
    mass_api.CreateMassAttr().Set(500.0)
    print(f"   ⚖️ 质量: 500 kg")

    # 关键：移除原始的Mesh碰撞体，只使用简单的碰撞体
    # 先移除已有的CollisionAPI（如果有）
    if UsdPhysics.CollisionAPI.Get(main_prim):
        # 注意：不能直接删除，但可以覆盖
        pass

    # 创建一个新的简单碰撞体（包围盒）
    min_point, max_point = get_prim_bounds(main_prim)
    size = (max_point[0] - min_point[0],
            max_point[1] - min_point[1],
            max_point[2] - min_point[2])

    print(f"   📐 火车包围盒: 宽{size[0]:.2f}, 高{size[1]:.2f}, 长{size[2]:.2f}")

    # 添加碰撞体并设置为盒子
    collision_api = UsdPhysics.CollisionAPI.Apply(main_prim)
