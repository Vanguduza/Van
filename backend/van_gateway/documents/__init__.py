"""Governed document transformations.

OpenMuse provenance: behavior is adapted from CopilotKit/openmuse
@34b15bc80340e582fb8c25573646cfb0bbc5184d, especially
packages/integrations/src/pdf.ts (MIT). VAN retains its own authority/evidence model.
"""

from .models import DocumentField, DocumentFieldKind, DocumentRecord, DocumentStatus
from .service import DocumentService, DocumentServiceError

__all__ = [
    "DocumentField", "DocumentFieldKind", "DocumentRecord", "DocumentStatus",
    "DocumentService", "DocumentServiceError",
]
