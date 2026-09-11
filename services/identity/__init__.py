"""Cross-camera identity: temporal alignment, appearance, association (E5)."""

from services.identity.alignment import OffsetEstimate, estimate_offsets, misaligned
from services.identity.association import (
    AssociationConfig,
    SegmentTrack,
    associate,
    build_segment_tracks,
    entity_groups,
)
from services.identity.persistence import link_to_contract, links_for_run, write_links

__all__ = [
    "AssociationConfig",
    "OffsetEstimate",
    "SegmentTrack",
    "associate",
    "build_segment_tracks",
    "entity_groups",
    "estimate_offsets",
    "link_to_contract",
    "links_for_run",
    "misaligned",
    "write_links",
]
