#!/usr/bin/env bash

set -euo pipefail

ISAAC_ROOT="${ISAAC_ROOT:-/home/admin204/isaac}"
ISAAC_LAUNCHER="${ISAAC_LAUNCHER:-$ISAAC_ROOT/isaac-sim.sh}"

if [[ ! -x "$ISAAC_LAUNCHER" ]]; then
  echo "未找到 Isaac Sim 启动脚本: $ISAAC_LAUNCHER"
  echo "可先设置环境变量，例如:"
  echo "  export ISAAC_ROOT=/home/admin204/isaac"
  exit 1
fi

# 清理外部 Python / CUDA 环境，避免污染 Isaac Sim 自带运行时。
unset PYTHONPATH
unset CONDA_PREFIX
unset CONDA_DEFAULT_ENV
unset CONDA_EXE
unset CONDA_PROMPT_MODIFIER
unset _CE_CONDA
unset _CE_M
unset LD_LIBRARY_PATH

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

cd "$ISAAC_ROOT"
exec "$ISAAC_LAUNCHER" "$@"
