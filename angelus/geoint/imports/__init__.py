"""Session-bound browser data import bounded context.

Only this package owns unconfirmed uploaded bytes and import lifecycle state.
Catalogue assets and map documents remain owned by their established modules.
"""

from .service import ImportError, ImportService

__all__ = ["ImportError", "ImportService"]
