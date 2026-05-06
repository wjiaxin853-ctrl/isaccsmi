#!/usr/bin/env sh

set -e

TARGET_DIR="/media/admin204/0a368315-e845-4ec0-bb15-fc5749d19252/ubuntu412/jx/Metric3d/Metric3D/training"
TARGET_ENV="metric"

if [ -n "${CONDA_EXE:-}" ]; then
    CONDA_BASE=$(dirname "$(dirname "$CONDA_EXE")")
elif [ -d "$HOME/miniconda3" ]; then
    CONDA_BASE="$HOME/miniconda3"
elif [ -d "$HOME/anaconda3" ]; then
    CONDA_BASE="$HOME/anaconda3"
else
    echo "未找到 conda 安装目录。"
    exit 1
fi

. "$CONDA_BASE/etc/profile.d/conda.sh"

conda deactivate || true
cd "$TARGET_DIR"
conda activate "$TARGET_ENV"

echo "当前环境: ${CONDA_DEFAULT_ENV:-未激活}"
echo "当前目录: $(pwd)"
