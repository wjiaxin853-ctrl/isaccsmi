from pxr import Usd, UsdPhysics, UsdGeom, UsdShade, UsdLux, Gf
import omni.usd
import sys
import io
import os
import json
from datetime import datetime

# ========== 配置输出 ==========
output_dir = r"/isaccsmi/canshu"
os.makedirs(output_dir, exist_ok=True)

# 输出文件
params_path = os.path.join(output_dir, "train_params.json")
report_path = os.path.join(output_dir, "params_report.txt")
log_path = os.path.join(output_dir, "export_log.txt")

# 重定向输出
original_stdout = sys.stdout
sys.stdout = io.StringIO()

try:
    print("=" * 80)
    print("📊 火车参数导出脚本")
    print("=" * 80)

    stage = omni.usd.get_context().get_stage()

    if not stage:
        print("❌ 没有打开的场景")
        raise Exception("没有打开的场景")

    print(f"📁 当前Stage: {stage.GetRootLayer().realPath}\n")

    # ================================================
    # 1. 遍历所有Prim，找出所有Mesh
    # ================================================
    print("1️⃣ 扫描场景中的所有Mesh...")

    all_prims = list(stage.Traverse())
    print(f"   总Prim数量: {len(all_prims)}")

    # 找出所有Mesh
    all_meshes = []
    for prim in all_prims:
        if prim.GetTypeName() == "Mesh":
            all_meshes.append(prim)

    print(f"   找到Mesh数量: {len(all_meshes)}")

    # ================================================
    # 2. 识别火车部件
    # ================================================
    print("\n2️⃣ 识别火车部件...")

    train_parts = all_meshes  # 使用所有Mesh
    print(f"   使用 {len(train_parts)} 个Mesh作为部件\n")

    # ================================================
    # 3. 获取主部件信息
    # ================================================
    print("3️⃣ 分析主部件...")

    main_part = None
    max_vertices = 0

    for part in train_parts:
        try:
            mesh = UsdGeom.Mesh(part)
            points_attr = mesh.GetPointsAttr()
            if points_attr and points_attr.HasAuthoredValue():
                points = points_attr.Get()
                vertex_count = len(points) if points else 0
                if vertex_count > max_vertices:
                    max_vertices = vertex_count
                    main_part = part
        except Exception as e:
            pass

    if main_part:
        print(f"   主部件: {main_part.GetName()}")
        print(f"   顶点数: {max_vertices}")
    else:
        if train_parts:
            main_part = train_parts[0]
            print(f"   主部件: {main_part.GetName()} (使用第一个)")

    print()

    # ================================================
    # 4. 收集物理参数
    # ================================================
    print("4️⃣ 收集物理参数...")

    physics_params = {
        "gravity": 9.8,
        "gravity_direction": [0, -1, 0],
        "mass": 500.0,
        "velocity": [0, 0, 10],
        "starts_asleep": False
    }

    # 检查物理场景
    for prim in all_prims:
        if prim.GetTypeName() == "PhysicsScene":
            try:
                scene = UsdPhysics.Scene(prim)
                gravity_mag = scene.GetGravityMagnitudeAttr()
                if gravity_mag and gravity_mag.HasAuthoredValue():
                    physics_params["gravity"] = gravity_mag.Get()

                gravity_dir = scene.GetGravityDirectionAttr()
                if gravity_dir and gravity_dir.HasAuthoredValue():
                    gd = gravity_dir.Get()
                    physics_params["gravity_direction"] = [gd[0], gd[1], gd[2]]
                print(f"   ✅ 找到物理场景: {prim.GetPath()}")
                break
            except:
                pass

    # 检查主部件的物理属性
    if main_part:
        try:
            rigid = UsdPhysics.RigidBodyAPI.Get(stage, main_part.GetPath())
            if rigid:
                starts_asleep = rigid.GetStartsAsleepAttr()
                if starts_asleep and starts_asleep.HasAuthoredValue():
                    physics_params["starts_asleep"] = starts_asleep.Get()

                velocity = rigid.GetVelocityAttr()
                if velocity and velocity.HasAuthoredValue():
                    vel = velocity.Get()
                    physics_params["velocity"] = [vel[0], vel[1], vel[2]]

            mass_api = UsdPhysics.MassAPI.Get(stage, main_part.GetPath())
            if mass_api:
                mass = mass_api.GetMassAttr()
                if mass and mass.HasAuthoredValue():
                    physics_params["mass"] = mass.Get()
        except Exception as e:
            print(f"   ⚠️ 物理属性读取失败: {str(e)[:50]}")

    print(f"   ⚙️ 重力: {physics_params['gravity']} m/s²")
    print(f"   📐 重力方向: {physics_params['gravity_direction']}")
    print(f"   ⚖️ 质量: {physics_params['mass']} kg")
    print(f"   🚀 速度: {physics_params['velocity']} m/s")
    print(f"   😴 初始休眠: {physics_params['starts_asleep']}\n")

    # ================================================
    # 5. 收集部件位置信息
    # ================================================
    print("5️⃣ 收集部件位置信息...")

    part_positions = {}
    for part in train_parts:
        try:
            xformable = UsdGeom.Xformable(part)
            transform = xformable.GetLocalTransformation(Usd.TimeCode.Default())
            translation = transform.ExtractTranslation()
            part_positions[part.GetName()] = {
                "x": translation[0],
                "y": translation[1],
                "z": translation[2]
            }
        except Exception as e:
            part_positions[part.GetName()] = {"x": 0, "y": 0, "z": 0}

    print(f"   📍 记录了 {len(part_positions)} 个部件位置\n")

    # ================================================
    # 6. 收集光照参数
    # ================================================
    print("6️⃣ 收集光照参数...")

    lighting_params = {
        "distant_light_intensity": 3000,
        "distant_light_color": [1.0, 1.0, 1.0],
        "dome_light_intensity": 300
    }

    for prim in all_prims:
        if prim.GetTypeName() == "DistantLight":
            try:
                light = UsdLux.DistantLight(prim)
                intensity = light.GetIntensityAttr()
                if intensity and intensity.HasAuthoredValue():
                    lighting_params["distant_light_intensity"] = intensity.Get()
                color = light.GetColorAttr()
                if color and color.HasAuthoredValue():
                    c = color.Get()
                    lighting_params["distant_light_color"] = [c[0], c[1], c[2]]
                print(f"   ✅ 找到方向光: {prim.GetPath()}")
            except:
                pass
        elif prim.GetTypeName() == "DomeLight":
            try:
                light = UsdLux.DomeLight(prim)
                intensity = light.GetIntensityAttr()
                if intensity and intensity.HasAuthoredValue():
                    lighting_params["dome_light_intensity"] = intensity.Get()
                print(f"   ✅ 找到环境光: {prim.GetPath()}")
            except:
                pass

    print(f"   💡 方向光强度: {lighting_params['distant_light_intensity']}")
    print(f"   🌐 环境光强度: {lighting_params['dome_light_intensity']}\n")

    # ================================================
    # 7. 收集材质参数
    # ================================================
    print("7️⃣ 收集材质参数...")

    material_params = {
        "materials": []
    }

    for prim in all_prims:
        if prim.GetTypeName() == "Material":
            material_info = {
                "name": prim.GetName(),
                "path": str(prim.GetPath())
            }
            material_params["materials"].append(material_info)

    print(f"   📦 找到 {len(material_params['materials'])} 个材质\n")

    # ================================================
    # 8. 构建完整参数配置
    # ================================================
    print("8️⃣ 构建完整参数配置...")

    full_config = {
        "version": "2.0",
        "export_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "stage_info": {
            "file_path": stage.GetRootLayer().realPath,
            "total_prims": len(all_prims),
            "mesh_count": len(all_meshes)
        },
        "model_info": {
            "part_count": len(train_parts),
            "main_part_name": main_part.GetName() if main_part else "None",
            "main_part_vertices": max_vertices,
            "parts_list": [p.GetName() for p in train_parts],
            "parts_paths": [str(p.GetPath()) for p in train_parts]
        },
        "physics": physics_params,
        "lighting": lighting_params,
        "materials": material_params,
        "positions": part_positions
    }

    # ================================================
    # 9. 保存为JSON文件
    # ================================================
    print("9️⃣ 保存参数文件...")

    with open(params_path, 'w', encoding='utf-8') as f:
        json.dump(full_config, f, indent=2, ensure_ascii=False)
    print(f"   ✅ JSON参数: {params_path}")

    # ================================================
    # 10. 生成可读报告
    # ================================================
    print("🔟 生成可读报告...")

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("火车参数配置报告\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")

        f.write("📌 Stage信息\n")
        f.write("-" * 40 + "\n")
        f.write(f"文件路径: {full_config['stage_info']['file_path']}\n")
        f.write(f"总Prim数: {full_config['stage_info']['total_prims']}\n")
        f.write(f"Mesh数量: {full_config['stage_info']['mesh_count']}\n\n")

        f.write("📌 模型信息\n")
        f.write("-" * 40 + "\n")
        f.write(f"部件数量: {full_config['model_info']['part_count']}\n")
        f.write(f"主部件: {full_config['model_info']['main_part_name']}\n")
        f.write(f"主部件顶点数: {full_config['model_info']['main_part_vertices']}\n\n")

        f.write("📌 物理参数\n")
        f.write("-" * 40 + "\n")
        f.write(f"重力: {physics_params['gravity']} m/s²\n")
        f.write(f"重力方向: {physics_params['gravity_direction']}\n")
        f.write(f"质量: {physics_params['mass']} kg\n")
        f.write(f"速度: {physics_params['velocity']} m/s\n")
        f.write(f"初始休眠: {physics_params['starts_asleep']}\n\n")

        f.write("📌 光照参数\n")
        f.write("-" * 40 + "\n")
        f.write(f"方向光强度: {lighting_params['distant_light_intensity']}\n")
        f.write(f"方向光颜色: {lighting_params['distant_light_color']}\n")
        f.write(f"环境光强度: {lighting_params['dome_light_intensity']}\n\n")

        f.write("📌 材质列表\n")
        f.write("-" * 40 + "\n")
        for mat in material_params['materials']:
            f.write(f"   - {mat['name']}: {mat['path']}\n")

        f.write("\n📌 部件位置\n")
        f.write("-" * 40 + "\n")
        for name, pos in part_positions.items():
            f.write(f"   {name}: X={pos['x']:.1f}, Y={pos['y']:.1f}, Z={pos['z']:.1f}\n")

    print(f"   ✅ 可读报告: {report_path}\n")

    # ================================================
    # 11. 总结
    # ================================================
    print("=" * 80)
    print("✅ 参数导出完成！")
    print("=" * 80)
    print(f"\n📁 输出目录: {output_dir}")
    print(f"\n📄 生成的文件:")
    print(f"   ├── train_params.json  : JSON格式参数")
    print(f"   ├── params_report.txt  : 可读报告")
    print(f"   └── export_log.txt     : 执行日志")
    print("\n📌 导出的参数包含:")
    print(f"   - 部件信息: {len(train_parts)} 个部件")
    print(f"   - 物理参数: 重力、质量、速度")
    print(f"   - 光照参数: 光源强度")
    print(f"   - 材质信息: {len(material_params['materials'])} 个材质")
    print(f"   - 位置信息: 所有部件坐标")
    print("=" * 80)

except Exception as e:
    print("=" * 80)
    print("❌ 脚本执行出错！")
    print("=" * 80)
    print(f"错误: {str(e)}")
    import traceback

    print(traceback.format_exc())

# ========== 保存输出 ==========
output_content = sys.stdout.getvalue()
sys.stdout = original_stdout

with open(log_path, "w", encoding="utf-8") as f:
    f.write(output_content)

print(f"✅ 日志已保存到: {log_path}")
print(f"✅ 参数文件已保存到: {output_dir}")