"""
Représente l'état d'une connexion SMTP et dispatche chaque ligne de
commande (hors mode DATA) vers commands/delivery.py.

Comme pour ImapSession, conçue pour être testable sans socket :
handle_command() et finish_data() sont des fonctions synchrones pures.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..commands import delivery
from .session_state import SmtpState


@dataclass
class SmtpSession:
    account_store: object
    backend: object
    relay_domains: list[str] = field(default_factory=list)
    relay_map: dict[str, tuple[str, int]] = field(default_factory=dict)
    state: SmtpState = SmtpState.INIT
    client_hostname: str | None = None
    mail_from: str | None = None
    rcpt_to: list[str] = field(default_factory=list)
    in_data_mode: bool = False

    def handle_command(self, verb: str, arg: str) -> list[str]:
        verb_upper = verb.upper()

        if verb_upper in ("HELO", "EHLO"):
            return delivery.handle_helo(self, arg)
        if verb_upper == "MAIL":
            return delivery.handle_mail(self, arg)
        if verb_upper == "RCPT":
            return delivery.handle_rcpt(self, arg)
        if verb_upper == "DATA":
            lines, should_enter_data_mode = delivery.handle_data_start(self)
            self.in_data_mode = should_enter_data_mode
            return lines
        if verb_upper == "RSET":
            return delivery.handle_rset(self)
        if verb_upper == "NOOP":
            return delivery.handle_noop(self)
        if verb_upper == "QUIT":
            return delivery.handle_quit(self)

        return [f"502 Command not implemented: {verb}"]

    def finish_data(self, raw_message: bytes) -> list[str]:
        """Appelée par le serveur TCP quand la ligne de fin '.' est reçue."""
        self.in_data_mode = False
        return delivery.handle_data_end(self, raw_message)