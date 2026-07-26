"""Modèles de données pour le stockage des messages (Maildir)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Flag(Enum):
    """
    Les 5 flags standards IMAP, chacun associé à sa lettre dans la
    convention de nommage Maildir (info-suffixe ":2,<lettres triées>").
    Référence: https://cr.yp.to/proto/maildir.html
    """

    SEEN = ("\\Seen", "S")
    ANSWERED = ("\\Answered", "R")
    FLAGGED = ("\\Flagged", "F")
    DELETED = ("\\Deleted", "T")
    DRAFT = ("\\Draft", "D")

    def __init__(self, imap_name: str, maildir_letter: str):
        self.imap_name = imap_name
        self.maildir_letter = maildir_letter

    @classmethod
    def from_imap_name(cls, name: str) -> "Flag":
        for flag in cls:
            if flag.imap_name.lower() == name.lower():
                return flag
        raise ValueError(f"Flag IMAP inconnu : {name}")

    @classmethod
    def from_maildir_letter(cls, letter: str) -> "Flag":
        for flag in cls:
            if flag.maildir_letter == letter:
                return flag
        raise ValueError(f"Lettre de flag Maildir inconnue : {letter}")


@dataclass
class Message:
    """
    Représente un message stocké, tel qu'exposé par le backend.

    uid: identifiant stable, unique au sein d'une mailbox (persiste tant
         que le message n'est pas expunge)
    filename: nom de fichier actuel sur disque, dans new/ ou cur/
    flags: ensemble de Flag actuellement posés sur le message
    raw: contenu brut du message (bytes). None si pas chargé (listing léger).
    """

    uid: int
    filename: str
    flags: set[Flag] = field(default_factory=set)
    raw: bytes | None = None

    def has_flag(self, flag: Flag) -> bool:
        return flag in self.flags

    def flags_imap(self) -> list[str]:
        return [f.imap_name for f in sorted(self.flags, key=lambda f: f.imap_name)]