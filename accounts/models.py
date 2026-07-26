"""Modèle de données représentant un compte utilisateur."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Account:
    username: str
    password_hash: str
    salt: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "username": self.username,
            "password_hash": self.password_hash,
            "salt": self.salt,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(data: dict) -> "Account":
        return Account(
            username=data["username"],
            password_hash=data["password_hash"],
            salt=data["salt"],
            created_at=data.get("created_at", ""),
        )