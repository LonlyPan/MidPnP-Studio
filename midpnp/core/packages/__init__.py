"""封装库（Package）与封装匹配。"""

from .library import (
    MatchReport,
    MatchResult,
    PackageDef,
    PackageLibrary,
    PadDef,
    compact_key,
    default_package_paths,
    normalize_footprint,
)

__all__ = [
    "MatchReport",
    "MatchResult",
    "PackageDef",
    "PackageLibrary",
    "PadDef",
    "compact_key",
    "default_package_paths",
    "normalize_footprint",
]
