"""Small, model-agnostic result types shared by every Import/Export service."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RowError:
    """Every problem found on one row of an uploaded file (1 = header row)."""

    row: int
    errors: list[str]

    def as_dict(self) -> dict:
        return {"row": self.row, "errors": self.errors}


@dataclass
class ImportPreview:
    total: int
    valid: int
    invalid: int
    errors: list[RowError] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "valid": self.valid,
            "invalid": self.invalid,
            "errors": [error.as_dict() for error in self.errors],
        }


@dataclass
class ImportResult:
    created: int
    updated: int
    total: int

    def as_dict(self) -> dict:
        return {"created": self.created, "updated": self.updated, "total": self.total}
