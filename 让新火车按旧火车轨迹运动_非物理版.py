import os

from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics


SCENE_USD = r"C:\Users\522\isaac-sim\data\Collected_train\train_with_new_train.usd"
OUTPUT_USD = r"C:\Users\522\isaac-sim\data\Collected_train\train_with_new_train_animated.usd"

OLD_TRAIN_ROOT = "/World/AM223_04"
NEW_TRAIN_ROOT = "/World/NewTrain"

# 按参考场景里常用的 24fps / 200帧 生成直线运动
START_FRAME = 1
END_FRAME = 200
FPS = 24


def get_required_prim(stage, prim_path):
    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsValid():
        raise RuntimeError(f"找不到 Prim: {prim_path}")
    return prim


def get_or_create_translate_op(xformable):
    for op in xformable.GetOrderedXformOps():
        if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
            return op
    return xformable.AddTranslateOp()


def get_translate_value(xformable):
    for op in xformable.GetOrderedXformOps():
        if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
            value = op.Get()
            return Gf.Vec3d(float(value[0]), float(value[1]), float(value[2]))
    return Gf.Vec3d(0.0, 0.0, 0.0)


def disable_rigidbody_motion(prim):
    rb = UsdPhysics.RigidBodyAPI(prim)
    if rb:
        rb.CreateRigidBodyEnabledAttr().Set(False)
        rb.CreateVelocityAttr().Set(Gf.Vec3f(0.0, 0.0, 0.0))
        rb.CreateAngularVelocityAttr().Set(Gf.Vec3f(0.0, 0.0, 0.0))


def main():
    if not os.path.exists(SCENE_USD):
        raise RuntimeError(f"场景不存在: {SCENE_USD}")

    stage = Usd.Stage.Open(SCENE_USD)
    if stage is None:
        raise RuntimeError(f"无法打开场景: {SCENE_USD}")

    old_prim = get_required_prim(stage, OLD_TRAIN_ROOT)
    new_prim = get_required_prim(stage, NEW_TRAIN_ROOT)

    old_xform = UsdGeom.Xformable(old_prim)
    new_xform = UsdGeom.Xformable(new_prim)

    old_translate = get_translate_value(old_xform)
    new_translate = get_translate_value(new_xform)

    # 旧火车沿 +Y 方向运动；参考旧场景物理速度取 5 m/s
    velocity_y = 5.0
    duration = (END_FRAME - START_FRAME) / FPS
    delta_y = velocity_y * duration

    start_translate = Gf.Vec3d(new_translate[0], old_translate[1], new_translate[2])
    end_translate = Gf.Vec3d(start_translate[0], start_translate[1] + delta_y, start_translate[2])

    translate_op = get_or_create_translate_op(new_xform)
    translate_op.Set(start_translate, Usd.TimeCode(START_FRAME))
    translate_op.Set(end_translate, Usd.TimeCode(END_FRAME))

    # 关闭根节点刚体，避免旋转、飞车。
    disable_rigidbody_motion(new_prim)

    stage.SetStartTimeCode(START_FRAME)
    stage.SetEndTimeCode(END_FRAME)
    stage.SetFramesPerSecond(FPS)
    stage.SetTimeCodesPerSecond(FPS)

    print(f"旧火车当前平移: {tuple(old_translate)}")
    print(f"新火车起点平移: {tuple(start_translate)}")
    print(f"新火车终点平移: {tuple(end_translate)}")
    print(f"动画帧范围: {START_FRAME} -> {END_FRAME} @ {FPS}fps")

    stage.GetRootLayer().Export(OUTPUT_USD)
    print(f"已输出场景: {OUTPUT_USD}")


main()
