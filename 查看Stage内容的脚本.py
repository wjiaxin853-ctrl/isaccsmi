import os
import traceback
import carb
from pxr import Usd
import omni.usd

# ==================== 输出到文件逻辑（每次运行都追加） ====================
output_file = r"C:\Users\522\Desktop\code\output.txt"


def log_to_file(message):
    try:
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, "a", encoding="utf-8") as f:
            f.write(message + "\n")
    except Exception as e:
        carb.log_error(f"无法写入输出文件: {str(e)}")


# 开始记录
log_to_file("\n" + "=" * 80)
log_to_file(f"脚本运行开始 - Stage 诊断 (使用 carb.log)")
log_to_file("=" * 80)

try:
    carb.log_info("=" * 80)
    carb.log_info("Omniverse Stage 诊断脚本开始（carb.log 版本）")
    carb.log_info("=" * 80)
    log_to_file("Omniverse Stage 诊断脚本开始（carb.log 版本）")

    stage = omni.usd.get_context().get_stage()

    pseudo_root = stage.GetPseudoRoot()
    msg = f"Pseudo Root: {pseudo_root.GetPath()}"
    carb.log_info(msg)
    log_to_file(msg)

    root_children = pseudo_root.GetChildren()
    msg = f"直接根节点数量: {len(root_children)}"
    carb.log_info(msg)
    log_to_file(msg)

    for prim in root_children:
        msg = f" 📁 {prim.GetName()} ({prim.GetTypeName()}) → {prim.GetPath()}"
        carb.log_info(msg)
        log_to_file(msg)

    # 搜索火车
    carb.log_info("\n=== 搜索火车相关 Prim ===")
    log_to_file("\n=== 搜索火车相关 Prim ===")
    found = False
    for prim in stage.Traverse():
        path_str = str(prim.GetPath())
        if "Obj3d66" in path_str or "/root" in path_str.lower():
            msg = f"   → {path_str}  ({prim.GetTypeName()})"
            carb.log_info(msg)
            log_to_file(msg)
            found = True
    if not found:
        msg = "   未找到火车相关 Prim（Obj3d66 或 root），请确认模型是否已导入"
        carb.log_info(msg)
        log_to_file(msg)

    total = len(list(stage.Traverse()))
    msg = f"\n总 Prim 数量: {total}"
    carb.log_info(msg)
    log_to_file(msg)

    carb.log_info("=== 诊断脚本执行完成 ===")
    log_to_file("=== 诊断脚本执行完成 ===")

except Exception as e:
    error_msg = f"❌ 发生错误: {str(e)}\n{traceback.format_exc()}"
    carb.log_error(error_msg)
    log_to_file(error_msg)

carb.log_info(f"✅ 输出已保存到文件: {output_file}")
log_to_file(f"✅ 输出已保存到文件: {output_file}")