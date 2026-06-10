#!/usr/bin/env bash
# Batch 3: torch CPU wheel + librosa + soundfile + timm + pytest
# Uses tsinghua mirror for everything except torch (which goes via pytorch.org cpu index).
set -e
LOG=/var/log/gm-deploy/batch3.log
mkdir -p /var/log/gm-deploy
: > "$LOG"
{
  echo "==== START $(date -Is) ===="
  cd /opt/gm-backend
  echo "---- pytorch.org cpu index probe ----"
  curl -sS -m 10 -o /dev/null -w "pytorch cpu index: %{http_code} time=%{time_total}s\n" \
    https://download.pytorch.org/whl/cpu/torch_stable.html || true
  echo "---- step 3a: torch CPU stack ----"
  ./.venv/bin/pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    --trusted-host pypi.tuna.tsinghua.edu.cn \
    --trusted-host download.pytorch.org \
    'torch==2.2.0+cpu' \
    'torchaudio==2.2.0+cpu' \
    'torchvision==0.17.0+cpu'
  echo "---- step 3b: librosa + soundfile + timm + pytest ----"
  ./.venv/bin/pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn \
    'librosa==0.10.2' \
    'soundfile==0.12.1' \
    'timm==1.0.3' \
    'pytest==8.3.5' \
    'pytest-asyncio==0.25.3'
  rc=$?
  echo "==== END rc=$rc $(date -Is) ===="
  echo "BATCH3_DONE_RC_$rc"
} >> "$LOG" 2>&1
