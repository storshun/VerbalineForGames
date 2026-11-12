#!/bin/bash
# Installs Step-Audio-EditX (StepFun, Apache 2.0) for ✦ Restyle's "edit the clip itself" engine:
# its code in ~/AI/Step-Audio-EditX, its models in ~/AI/step-audio-models, and its own Python (3.12, PyTorch 2.9, vLLM)
# in ~/AI/stepaudio-env, from its own lock file. About 15 GB in all. Then point the studio at them, in
# ~/.config/verbaline/config.toml:
#   [repos]  step_audio_editx = "~/AI/Step-Audio-EditX"    step_audio_models = "~/AI/step-audio-models"
#   [envs]   editx = "~/AI/stepaudio-env/bin/python"
# and restart the studio; it offers the engine as soon as they exist.
set -euo pipefail
AI=~/AI
if [ ! -d "$AI/Step-Audio-EditX/.git" ]; then
    git clone --depth 1 https://github.com/stepfun-ai/Step-Audio-EditX.git "$AI/Step-Audio-EditX"
fi
cd "$AI/Step-Audio-EditX"
# Its locked versions (torch 2.9.1, vLLM 0.14) into their own environment, apart from the studio's three.
UV_PROJECT_ENVIRONMENT="$AI/stepaudio-env" uv sync --frozen --python 3.12
"$AI/stepaudio-env/bin/python" - <<'EOF'
from huggingface_hub import snapshot_download
import os
for r in ('stepfun-ai/Step-Audio-Tokenizer', 'stepfun-ai/Step-Audio-EditX'):
    print(snapshot_download(r, local_dir=os.path.expanduser('~/AI/step-audio-models/' + r.split('/')[1])))
EOF
"$AI/stepaudio-env/bin/python" -c "import torch, vllm; print('torch', torch.__version__, 'cuda', torch.cuda.is_available(), 'vllm', vllm.__version__)"
echo "Step-Audio-EditX installed. Point ~/.config/verbaline/config.toml at it (see the top of this script), then restart the studio."
