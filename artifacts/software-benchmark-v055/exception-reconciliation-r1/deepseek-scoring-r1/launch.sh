#!/usr/bin/env bash
set -euo pipefail
exec systemd-run --user --unit=proworksim-v055-exception-scoring-r1 --service-type=exec \
  --property=Restart=no --property=KillMode=control-group \
  --working-directory=/data0/zhuxinrui/projects/ProWorkSim \
  /usr/bin/env PYTHONPATH=/data0/zhuxinrui/projects/ProWorkSim/src PYTHONDONTWRITEBYTECODE=1 \
  HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= http_proxy= https_proxy= all_proxy= NO_PROXY='*' no_proxy='*' \
  CUDA_VISIBLE_DEVICES= NVIDIA_VISIBLE_DEVICES=void \
  /data0/zhuxinrui/projects/ProWorkSim/.venv/bin/python -B \
  /data0/zhuxinrui/projects/ProWorkSim/tools/reconcile_deepseek_scores_v055_r1.py run \
  --plan /data0/zhuxinrui/projects/ProWorkSim/runs/software-benchmark-v055/exception-reconciliation-r1/deepseek-scoring-r1/plan.json \
  --sha256 57a89757cf6b9bfb4a3db1b55e4180480261703da7823b0b2016445398dd9622 --workers 4
