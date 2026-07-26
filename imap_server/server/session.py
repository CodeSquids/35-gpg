"""
Représente l'état d'une connexion IMAP et dispatche chaque commande reçue
vers le handler approprié dans commands/.

Conçue pour être testable sans aucun socket : ImapSession.handle_command()
est une fonction synchrone pure (état -> lignes de réponse), ce qui permet
de tester toute la state machine et les commandes en pytest classique.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..commands import auth, mailbox, messages
from .session_state import SessionState


@dataclass
class ImapSession:
    account_store: object
    backend: object
    state: SessionState = SessionState.NOT_AUTHENTICATED
    username: str | None = None
    selected_mailbox: str | None = None
    readonly: bool = False

    def handle_command(self, tag: str, name: str, args: list[str]) -> list[str]:
        handler = _DISPATCH.get(name)
        if handler is None:
            return [f"{tag} BAD Unknown command: {name}"]
        return handler(self, tag, args)


_DISPATCH = {
    "CAPABILITY": auth.handle_capability,
    "REGISTER": auth.handle_register,
    "LOGIN": auth.handle_login,
    "LOGOUT": auth.handle_logout,
    "SELECT": mailbox.handle_select,
    "EXAMINE": mailbox.handle_examine,
    "LIST": mailbox.handle_list,
    "CREATE": mailbox.handle_create,
    "DELETE": mailbox.handle_delete,
    "RENAME": mailbox.handle_rename,
    "SUBSCRIBE": mailbox.handle_subscribe,
    "UNSUBSCRIBE": mailbox.handle_unsubscribe,
    "FETCH": messages.handle_fetch,
    "STORE": messages.handle_store,
    "SEARCH": messages.handle_search,
    "EXPUNGE": messages.handle_expunge,
    "NOOP": messages.handle_noop,
}