"""AiApiRadar — multi-source monitor for free AI API credit / trial offers."""
import pathlib as _pathlib

# Version is the single source of truth in the root VERSION file.
# Falls back to "dev" if running outside the project (e.g. installed as a package).
try:
    __version__ = (_pathlib.Path(__file__).parent.parent / "VERSION").read_text().strip()
except Exception:
    __version__ = "dev"
