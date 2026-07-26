"""
Commandes du groupe AUTHENTICATION : CAPABILITY, LOGIN, LOGOUT, et
l'extension REGISTER (non-standard, ajoutée pour permettre la création de
compte directement via le protocole -- cf. ROADMAP.md, Étape 3).
"""

from __future__ import annotations

from accounts import AccountAlreadyExistsError, InvalidCredentialsError
from accounts.store import InvalidUsernameError

from ..server.session_state import SessionState


def handle_capability(session, tag, args):
    # CAPABILITY est volontairement "neutre" : elle ne doit JAMAIS modifier
    # session.state. C'est précisément l'inverse de ça qui causait le bug
    # d'origine (LOGIN refusé juste après un CAPABILITY).
    return [
        "* CAPABILITY IMAP4REV1 IMAP4",
        f"{tag} OK CAPABILITY completed",
    ]


def handle_register(session, tag, args):
    """
    Extension non-standard : REGISTER <username> <password>
    Uniquement autorisée avant authentification (comme LOGIN).
    """
    if session.state != SessionState.NOT_AUTHENTICATED:
        return [f"{tag} NO Cannot REGISTER in current state"]
    if len(args) < 2:
        return [f"{tag} BAD REGISTER requires a username and a password"]

    username, password = args[0], args[1]
    try:
        session.account_store.create_account(username, password)
    except InvalidUsernameError as e:
        return [f"{tag} NO {e}"]
    except AccountAlreadyExistsError as e:
        return [f"{tag} NO {e}"]
    except ValueError as e:
        return [f"{tag} NO {e}"]

    session.backend.ensure_mailbox(username, "INBOX")
    return [f"{tag} OK REGISTER completed"]


def handle_login(session, tag, args):
    if session.state != SessionState.NOT_AUTHENTICATED:
        return [f"{tag} NO Cannot LOGIN in current state"]
    if len(args) < 2:
        return [f"{tag} BAD LOGIN requires a username and a password"]

    username, password = args[0], args[1]
    try:
        session.account_store.verify_password(username, password)
    except InvalidCredentialsError:
        return [f"{tag} NO LOGIN failed"]

    session.state = SessionState.AUTHENTICATED
    session.username = username
    session.backend.ensure_mailbox(username, "INBOX")
    return [f"{tag} OK LOGIN completed"]


def handle_logout(session, tag, args):
    session.state = SessionState.LOGOUT
    return [
        "* BYE LOGOUT requested",
        f"{tag} OK LOGOUT completed",
    ]