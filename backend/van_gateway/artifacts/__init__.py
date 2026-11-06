"""Owner-facing artifact projection.

Artifacts are presentation/retrieval projections over canonical VAN evidence. They never
become a second truth store or mutation authority.
"""

from .models import ArtifactKind, ArtifactSensitivity, OwnerArtifact
from .service import ArtifactService, ArtifactServiceError

__all__ = [
    "ArtifactKind", "ArtifactSensitivity", "OwnerArtifact",
    "ArtifactService", "ArtifactServiceError",
]
