#!/usr/bin/env bash
# Batch 2: scientific stack via tsinghua mirror.
set -e
LOG=/var/log/gm-deploy/batch2.log
mkdir -p /var/log/gm-deploy
: > "$LOG"
{
  echo "==== START $(date -Is) ===="
  cd /opt/gm-backend
  ./.venv/bin/pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn \
    'numpy==1.26.4' \
    'scipy==1.12.0' \
    'scikit-learn==1.4.0' \
    'pandas==2.2.0' \
    'matplotlib==3.8.3'
  rc=$?
  echo "==== END rc=$rc $(date -Is) ===="
  echo "BATCH2_DONE_RC_$rc"
} >> "$LOG" 2>&1
