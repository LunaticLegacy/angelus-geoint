"""Core-scoped composition for the GEOINT bounded context.

HTTP adapters and Agent tools deliberately receive this one runtime rather
than constructing catalogues or map stores themselves.  It is owned by
``AngelusCore`` and therefore follows its configured state root.
"""

from __future__ import annotations

from pathlib import Path

from ..assets import GeoAssetCatalog
from ..mapping import MapPresentationStore
from ..processing import DerivationService
from ..analysis import GeoIntService
from ..evidence import EvidenceStore
from ..ingestion import ImportService
from ..knowledge import DroughtKnowledgeBase


class GeoIntRuntime:
    """Own all process-local GEOINT services for one :class:`AngelusCore`."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = state_root.resolve()
        self.root = self.state_root / "geoint"
        self.service = GeoIntService(state_root=self.root)
        self.catalog: GeoAssetCatalog = self.service._require_catalog()
        self.derivations = DerivationService(self.catalog, self.root / "derived")
        # GeoIntService predates the core runtime.  Point its public service
        # reference to this managed derivation service so legacy callers do
        # not create a second job registry or write outside Angelus state.
        self.service.derivations = self.derivations
        self.evidence = EvidenceStore(self.root / "evidence")
        self.knowledge = DroughtKnowledgeBase()
        self.downloads = (self.root / "downloads").resolve()
        self.presentation = MapPresentationStore(
            self.state_root,
            lambda session_id, asset_id: self.catalog.bound_asset(session_id, asset_id),
        )
        # The core installs the Session existence guard once its workspace
        # catalogue has been restored.  Keeping the callback injected avoids a
        # GEOINT dependency on Angelus's Session implementation.
        self.imports: ImportService | None = None

    def configure_session_guard(self, session_exists) -> None:
        self.imports = ImportService(self.root / "imports", self.catalog, self.presentation, session_exists)


__all__ = ["GeoIntRuntime"]
