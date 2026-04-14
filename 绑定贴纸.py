import sys
import io
import os
import traceback
import re
import omni.usd
from pxr import Usd, UsdShade, Sdf, Gf

# ========== 重定向输出 ==========
output_dir = r"C:\Users\522\Desktop\code"
os.makedirs(output_dir, exist_ok=True)

original_stdout = sys.stdout
sys.stdout = io.StringIO()

# ========== 你的代码 ==========
try:
    def log(msg):
        print(msg)


    log("=" * 60)
    log("使用 OmniPBR 材质重新绑定贴图（修正版 v2）")
    log("=" * 60)

    TEXTURE_DIR = r"C:\Users\522\Downloads\data\png"
    stage = omni.usd.get_context().get_stage()

    if not stage:
        log("❌ 没有打开的场景")
    else:
        root = stage.GetPrimAtPath("/root")
        if not root:
            log("❌ 找不到 /root")
        else:
            fixed_count = 0

            for child in root.GetChildren():
                if child.GetTypeName() != "Mesh":
                    continue

                mesh_name = child.GetName()

                # 从部件名称提取编号
                match = re.search(r'(\d+)', mesh_name)
                if not match:
                    log(f"\n⏭️ {mesh_name}: 无法提取编号，跳过")
                    continue

                material_num = int(match.group(1))

                # 查找贴图
                texture_path = None
                texture_name = None
                for offset in range(-5, 6):
                    candidate = material_num + offset
                    if 1 <= candidate <= 314:
                        candidate_name = f"3d66Model-1238088-files-{candidate}.png"
                        candidate_path = os.path.join(TEXTURE_DIR, candidate_name)
                        if os.path.exists(candidate_path):
                            texture_path = candidate_path
                            texture_name = candidate_name
                            break

                if not texture_path:
                    log(f"\n⏭️ {mesh_name}: 未找到贴图")
                    continue

                try:
                    log(f"\n📦 {mesh_name} -> 贴图: {texture_name}")

                    # 创建材质
                    material_path = f"/root/OmniPBR_{material_num}"
                    material_prim = stage.GetPrimAtPath(material_path)
                    if not material_prim:
                        material_prim = stage.DefinePrim(material_path, "Material")
                        log(f"   创建材质: OmniPBR_{material_num}")

                    material = UsdShade.Material(material_prim)

                    # 创建 Shader
                    shader_path = f"{material_path}/Shader"
                    shader_prim = stage.GetPrimAtPath(shader_path)
                    if not shader_prim:
                        shader_prim = stage.DefinePrim(shader_path, "Shader")

                    shader = UsdShade.Shader(shader_prim)
                    shader.CreateIdAttr("OmniPBR")

                    # 创建纹理节点
                    tex_path = f"{material_path}/diffuse_texture"
                    tex_prim = stage.GetPrimAtPath(tex_path)
                    if not tex_prim:
                        tex_prim = stage.DefinePrim(tex_path, "Shader")

                    tex = UsdShade.Shader(tex_prim)
                    tex.CreateIdAttr("UsdUVTexture")
                    tex.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(texture_path.replace("\\", "/"))
                    tex.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)

                    # 连接纹理到 Shader
                    shader.CreateInput("diffuse_color_constant", Sdf.ValueTypeNames.Color3f)
                    shader.GetInput("diffuse_color_constant").ConnectToSource(tex.GetOutput("rgb"))

                    # 设置其他参数
                    shader.CreateInput("metallic_constant", Sdf.ValueTypeNames.Float).Set(0.0)
                    shader.CreateInput("roughness_constant", Sdf.ValueTypeNames.Float).Set(0.5)

                    # 连接 Shader 到材质
                    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")

                    # 绑定材质到模型 - 使用 MaterialBindingAPI
                    bindingAPI = UsdShade.MaterialBindingAPI(child)
                    bindingAPI.Bind(material)

                    log(f"   ✅ 已绑定 OmniPBR 材质")
                    fixed_count += 1

                except Exception as e:
                    log(f"   ❌ 处理 {mesh_name} 时出错: {str(e)}")
                    log(f"      详细: {traceback.format_exc()}")

            log(f"\n{'=' * 60}")
            log(f"修复完成！成功处理 {fixed_count} 个部件")
            log(f"{'=' * 60}")

except Exception as e:
    print("=" * 60)
    print("脚本执行出错！")
    print(f"错误: {str(e)}")
    print(traceback.format_exc())

# ========== 保存输出 ==========
output_content = sys.stdout.getvalue()
sys.stdout = original_stdout

output_path = os.path.join(output_dir, "output.txt")
with open(output_path, "w", encoding="utf-8") as f:
    f.write(output_content)

print(f"输出已保存到: {output_path}")