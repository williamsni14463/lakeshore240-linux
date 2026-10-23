"""Native Linux access to the Lake Shore 240 series temperature monitor."""

from .driver import LakeShore240, LakeShore240Error

__all__ = ["LakeShore240", "LakeShore240Error"]
