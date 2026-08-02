"""What a person change request is allowed to propose, and how staleness is judged.

Two rules live here, both pure and framework-agnostic:

1. ``SUBMITTABLE_PERSON_FIELDS`` — the subset of the Person aggregate's updatable
   fields a change request may propose. It is deliberately NARROWER than
   ``Person``'s own whitelist:

   - ``phone`` / ``email`` are contact PII. The review surface echoes the target's
     *current* value for every proposed field so the reviewer can see what would be
     overwritten; allowing PII here would leak an ordinary member's contact details
     to any editor through the queue, bypassing the redaction on the person read
     path. Contact details are not gia phả content and are not corrected by
     relatives, so excluding them costs nothing.
   - ``avatar_url`` is set by the document/avatar flow, not typed by a human, so it
     is not a "this fact is wrong" correction.

   The set is written out rather than derived from ``Person``'s private whitelist so
   production code never reads a private name; a unit test pins it against the
   aggregate's set so the two cannot drift.

2. ``detect_conflicts`` — the three-way merge rule that decides whether a proposal
   that was written against an older version of the record may still be applied.
   See ADR-037.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# Genealogy facts a relative can plausibly report as wrong. Compare against
# ``app.domain.person.entity``'s updatable-field whitelist (pinned by a unit test).
SUBMITTABLE_PERSON_FIELDS: frozenset[str] = frozenset(
    {
        "full_name",
        "birth_name",
        "courtesy_name",
        "posthumous_name",
        "alias_name",
        "gender",
        "birth_date",
        "birth_date_precision",
        "birth_date_display",
        "death_date",
        "death_date_precision",
        "death_date_display",
        "lunar_birth_date",
        "lunar_death_date",
        "birth_place",
        "death_place",
        "burial_place",
        "tomb_location",
        "residence_place",
        "religion",
        "nationality",
        "occupation",
        "education_level",
        "title_rank",
        "biography",
        "notes",
    }
)

# Excluded on purpose — see the module docstring. Kept explicit so the pinning test
# can assert the exclusion is deliberate rather than an oversight.
EXCLUDED_PERSON_FIELDS: frozenset[str] = frozenset({"phone", "email", "avatar_url"})


@dataclass(frozen=True)
class FieldConflict:
    """One proposed field whose target value moved to something else since submission."""

    field: str
    base: Any
    current: Any
    proposed: Any

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "base": self.base,
            "current": self.current,
            "proposed": self.proposed,
        }


def detect_conflicts(
    changes: Mapping[str, Any],
    base_values: Mapping[str, Any],
    current_values: Mapping[str, Any],
) -> list[FieldConflict]:
    """Three-way merge: which proposed fields can no longer be applied safely?

    All three mappings must already be in the SAME normalized (JSON) representation,
    otherwise ``1920-05-03`` and ``date(1920, 5, 3)`` would read as a conflict.

    A field conflicts iff the target moved AND it did not move to what this request
    proposes:

    - ``current == base`` — nobody touched this field since submission. Applying the
      proposal overwrites only the value the requester actually saw. **Safe.**
    - ``current == proposed`` — somebody already made this exact correction.
      Re-applying it is a no-op, not a lost update. **Safe.**
    - otherwise — somebody wrote a *different* value here after the requester read
      it. Applying the proposal would silently destroy that edit. **Conflict.**

    Fields the record moved on that this request does NOT propose are irrelevant: a
    week-old birth-date correction stays applicable after somebody rewrote the
    biography. That is the whole point of merging per field instead of per row.
    """
    conflicts: list[FieldConflict] = []
    for field_name, proposed in changes.items():
        base = base_values.get(field_name)
        current = current_values.get(field_name)
        if current != base and current != proposed:
            conflicts.append(
                FieldConflict(field=field_name, base=base, current=current, proposed=proposed)
            )
    return conflicts
