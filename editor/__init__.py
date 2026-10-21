"""Claude video editor engine."""

import os

# Set before anything imports huggingface_hub, which reads it once at import: Hugging Face's Xet download path
# (cas-server.xethub.hf.co) answers 401 behind the agent proxy; plain HTTPS works.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
