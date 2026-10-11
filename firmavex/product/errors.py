"""Structured administrator-facing failures, never strategy feedback."""

from __future__ import annotations

from typing import Any


class ProductError(Exception):
    def __init__(self, category: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.category = category
        self.message = message
        self.details = {} if details is None else dict(details)

    def to_dict(self) -> dict[str, Any]:
        return {"category": self.category, "message": self.message, "details": self.details}
