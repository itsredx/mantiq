# ── Nizam Build Backend (PEP 517 / PEP 518) ─────────────────────────────
"""PEP 517 / PEP 518 build backend for packaging Nizam modules as wheels."""

from .core import (
    build_wheel,
    build_sdist,
    get_requires_for_build_wheel,
    get_requires_for_build_sdist,
    prepare_metadata_for_build_wheel,
)

__all__ = [
    "build_wheel",
    "build_sdist",
    "get_requires_for_build_wheel",
    "get_requires_for_build_sdist",
    "prepare_metadata_for_build_wheel",
]
