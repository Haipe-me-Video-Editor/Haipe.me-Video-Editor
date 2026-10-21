"""Make resemble-enhance's inference importable on this stack: a deepspeed stub and a numpy 2 fix. Idempotent."""
import site
from pathlib import Path

sp = Path(site.getsitepackages()[0])
ds = sp / "deepspeed"
files = {
    "__init__.py": '"""Inference-only stub: resemble-enhance imports deepspeed for training only."""\n'
                   "class DeepSpeedConfig:\n    def __init__(self, *a, **k):\n        pass\n\n\n"
                   "def init_distributed(*a, **k):\n    pass\n\n\n"
                   "def initialize(*a, **k):\n    raise RuntimeError('deepspeed stub: training is not supported')\n",
    "accelerator/__init__.py": "def get_accelerator():\n    raise RuntimeError('deepspeed stub')\n",
    "runtime/__init__.py": "",
    "runtime/engine.py": "class DeepSpeedEngine:\n    pass\n",
    "runtime/utils.py": "def clip_grad_norm_(*a, **k):\n    pass\n",
}
if not (ds / "runtime" / "engine.py").exists():
    for rel, text in files.items():
        (ds / rel).parent.mkdir(parents=True, exist_ok=True)
        (ds / rel).write_text(text)
cfm = sp / "resemble_enhance" / "enhancer" / "lcfm" / "cfm.py"
src = cfm.read_text()
old = "x0=0))"
if "x0=0)[0])" not in src and old in src:
    cfm.write_text(src.replace(old, "x0=0)[0])"))
print("resemble-enhance patched")
