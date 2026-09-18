"""
Uniform application error, mirroring the TypeScript backend's AppError
(src/utils/errors.ts) — same status codes, same code vocabulary — so the
error *shape* on the wire stays familiar across both services during the
migration, even though nothing shares a process.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details

    @classmethod
    def bad_request(cls, message: str, details: Any = None) -> AppError:
        return cls(400, "BAD_REQUEST", message, details)

    @classmethod
    def unauthorized(cls, message: str = "Unauthorized") -> AppError:
        return cls(401, "UNAUTHORIZED", message)

    @classmethod
    def forbidden(cls, message: str = "Forbidden") -> AppError:
        return cls(403, "FORBIDDEN", message)

    @classmethod
    def not_found(cls, message: str = "Not Found") -> AppError:
        return cls(404, "NOT_FOUND", message)

    @classmethod
    def conflict(cls, message: str) -> AppError:
        return cls(409, "CONFLICT", message)
