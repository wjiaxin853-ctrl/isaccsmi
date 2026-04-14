import os

# 输入目录（你的数据目录）
input_dir = r"C:\Users\522\Downloads\1238088_07711214bf3dcb13d3b8e9ac84b3231f"

# 输出文件
output_file = r"C:\Users\522\Desktop\code\isaccsmi\output.txt"

# 确保输出目录存在
os.makedirs(os.path.dirname(output_file), exist_ok=True)

# 遍历目录
with open(output_file, "w", encoding="utf-8") as f:
    for root, dirs, files in os.walk(input_dir):
        for name in files:
            full_path = os.path.join(root, name)
            f.write(full_path + "\n")

print("文件列表已写入:", output_file)