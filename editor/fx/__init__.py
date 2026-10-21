"""Signature video effects (the "fx pack"), built in code on real footage: no AI-generated pixels. Each effect replaces a window of the picture.

Every effect is one module in this package with:
    NAME = "vertigo"                     # the edit.json / fx.json `type`
    DOC = "one line for the planner"
    BEST_FOR = ["finance", "product", ...]  # where it earns its place: any, finance, product, playful, corporate
    PARAMS = {"param": default, ...}     # every optional field, with its default
    def render(ctx: core.Ctx) -> Path    # writes ctx.out: an opaque clip exactly ctx.dur long at ctx.fps

Modules register themselves by being in this folder (no central list to edit). `apply.apply_fx` splices the
rendered windows back into the picture frame-exactly; `render` calls it on the cut base video, and the
`fx-apply` / `fx-sample` commands run it on any 9:16 clip.
"""
import importlib
import pkgutil

_SKIP = {"core", "apply"}


def registry() -> dict:
    """{type: module} for every effect module in this package."""
    out = {}
    for m in pkgutil.iter_modules(__path__):
        if m.name in _SKIP or m.name.startswith("_"):
            continue
        mod = importlib.import_module(f"{__name__}.{m.name}")
        if hasattr(mod, "NAME") and hasattr(mod, "render"):
            out[mod.NAME] = mod
    return out
