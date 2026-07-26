"""Commandes du groupe MAILBOX : SELECT, EXAMINE, LIST, CREATE, DELETE,
RENAME, SUBSCRIBE, UNSUBSCRIBE."""

from __future__ import annotations

import os
import shutil

from ..server.session_state import SessionState


def _require_authenticated(session, tag):
    if session.state not in (SessionState.AUTHENTICATED, SessionState.SELECTED):
        return [f"{tag} NO Please authenticate first"]
    return None


def handle_select(session, tag, args, readonly: bool = False):
    err = _require_authenticated(session, tag)
    if err:
        return err
    if not args:
        return [f"{tag} BAD SELECT requires a mailbox name"]

    mailbox_name = args[0]
    session.backend.ensure_mailbox(session.username, mailbox_name)

    messages = session.backend.list_messages(session.username, mailbox_name)
    recent = sum(1 for m in messages if not m.flags)  # pas de flag = jamais vu
    uidvalidity = session.backend.get_uidvalidity(session.username, mailbox_name)

    session.state = SessionState.SELECTED
    session.selected_mailbox = mailbox_name
    session.readonly = readonly

    mode = "READ-ONLY" if readonly else "READ-WRITE"
    completed_cmd = "EXAMINE" if readonly else "SELECT"

    return [
        "* FLAGS (\\Answered \\Flagged \\Draft \\Deleted \\Seen)",
        f"* {len(messages)} EXISTS",
        f"* {recent} RECENT",
        f"* OK [UIDVALIDITY {uidvalidity}] UIDs valid",
        "* OK [PERMANENTFLAGS (\\Answered \\Flagged \\Draft \\Deleted \\Seen)] Limited",
        f"{tag} OK [{mode}] {completed_cmd} completed",
    ]


def handle_examine(session, tag, args):
    return handle_select(session, tag, args, readonly=True)


def handle_list(session, tag, args):
    err = _require_authenticated(session, tag)
    if err:
        return err

    mailboxes = session.backend.list_mailboxes(session.username)
    if not mailboxes:
        session.backend.ensure_mailbox(session.username, "INBOX")
        mailboxes = ["INBOX"]

    lines = [f'* LIST () "/" {name}' for name in mailboxes]
    lines.append(f"{tag} OK LIST completed")
    return lines


def handle_create(session, tag, args):
    err = _require_authenticated(session, tag)
    if err:
        return err
    if not args:
        return [f"{tag} BAD CREATE requires a mailbox name"]
    session.backend.ensure_mailbox(session.username, args[0])
    return [f"{tag} OK CREATE completed"]


def handle_delete(session, tag, args):
    err = _require_authenticated(session, tag)
    if err:
        return err
    if not args:
        return [f"{tag} BAD DELETE requires a mailbox name"]

    base = session.backend._mailbox_dir(session.username, args[0])
    if not os.path.isdir(base):
        return [f"{tag} NO No such mailbox"]
    shutil.rmtree(base)
    return [f"{tag} OK DELETE completed"]


def handle_rename(session, tag, args):
    err = _require_authenticated(session, tag)
    if err:
        return err
    if len(args) < 2:
        return [f"{tag} BAD RENAME requires two mailbox names"]

    old_path = session.backend._mailbox_dir(session.username, args[0])
    new_path = session.backend._mailbox_dir(session.username, args[1])
    if not os.path.isdir(old_path):
        return [f"{tag} NO No such mailbox"]
    os.rename(old_path, new_path)
    return [f"{tag} OK RENAME completed"]


def handle_subscribe(session, tag, args):
    err = _require_authenticated(session, tag)
    if err:
        return err
    # Liste de souscription minimaliste : acceptée sans persistance séparée
    # (limitation assumée pour ce projet académique).
    return [f"{tag} OK SUBSCRIBE completed"]


def handle_unsubscribe(session, tag, args):
    err = _require_authenticated(session, tag)
    if err:
        return err
    return [f"{tag} OK UNSUBSCRIBE completed"]