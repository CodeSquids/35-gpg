"""Commandes du groupe MESSAGES : FETCH, STORE, SEARCH, EXPUNGE, NOOP."""

from __future__ import annotations

from storage import Flag

from ..server.session_state import SessionState

_IMAP_FLAG_BY_NAME = {
    "\\Seen": Flag.SEEN,
    "\\Answered": Flag.ANSWERED,
    "\\Flagged": Flag.FLAGGED,
    "\\Deleted": Flag.DELETED,
    "\\Draft": Flag.DRAFT,
}


def _require_selected(session, tag):
    if session.state != SessionState.SELECTED:
        return [f"{tag} NO Please select a mailbox first"]
    return None


def _parse_flag_list(tokens: list[str]) -> set[Flag]:
    """Reconstruit la liste de flags à partir de tokens du type
    ['(\\Seen', '\\Flagged)'] -> {Flag.SEEN, Flag.FLAGGED}."""
    joined = " ".join(tokens).strip()
    if joined.startswith("(") and joined.endswith(")"):
        joined = joined[1:-1]
    flags = set()
    for name in joined.split():
        flag = _IMAP_FLAG_BY_NAME.get(name)
        if flag is not None:
            flags.add(flag)
    return flags


def _extract_header(raw: bytes) -> bytes:
    for sep in (b"\r\n\r\n", b"\n\n"):
        idx = raw.find(sep)
        if idx != -1:
            return raw[:idx]
    return raw


def _expand_uid_set(spec: str, existing_uids: list[int]) -> set[int]:
    """
    Traduit une spécification d'ensemble d'UID IMAP ('1:*', '3,7,9',
    '1:3,7:9', '*'...) en un ensemble d'UID réellement présents.
    '*' représente le plus grand UID courant (comportement standard RFC 3501,
    utilisé par les vrais clients pour dire "jusqu'au dernier message").
    """
    if not existing_uids:
        return set()
    max_uid = max(existing_uids)
    uid_set = set(existing_uids)
    result: set[int] = set()

    for part in spec.split(","):
        if ":" in part:
            lo_raw, hi_raw = part.split(":", 1)
            lo = max_uid if lo_raw == "*" else int(lo_raw)
            hi = max_uid if hi_raw == "*" else int(hi_raw)
            if lo > hi:
                lo, hi = hi, lo
            result.update(uid for uid in uid_set if lo <= uid <= hi)
        else:
            uid = max_uid if part == "*" else int(part)
            if uid in uid_set:
                result.add(uid)

    return result


def handle_noop(session, tag, args):
    return [f"{tag} OK NOOP completed"]


def handle_fetch(session, tag, args):
    err = _require_selected(session, tag)
    if err:
        return err
    if len(args) < 2:
        return [f"{tag} BAD FETCH requires a message number and data items"]

    try:
        seq_num = int(args[0])
    except ValueError:
        return [f"{tag} BAD Invalid message number"]

    data_items = " ".join(args[1:]).upper()
    messages = session.backend.list_messages(
        session.username, session.selected_mailbox, include_raw=True
    )
    if seq_num < 1 or seq_num > len(messages):
        return [f"{tag} NO No such message"]

    message = messages[seq_num - 1]  # sequence number = position, triée par UID
    parts = []

    if "FLAGS" in data_items:
        parts.append(f"FLAGS ({' '.join(message.flags_imap())})")
    if "UID" in data_items:
        parts.append(f"UID {message.uid}")
    if "BODY[HEADER]" in data_items:
        header = _extract_header(message.raw)
        text = header.decode("utf-8", errors="replace")
        parts.append(f"BODY[HEADER] {{{len(header)}}}\r\n{text}")
    elif "BODY[]" in data_items:
        text = message.raw.decode("utf-8", errors="replace")
        parts.append(f"BODY[] {{{len(message.raw)}}}\r\n{text}")

    lines = [f"* {seq_num} FETCH ({' '.join(parts)})"]

    # Lire le corps ou l'en-tête d'un message (sauf en mode EXAMINE, lecture
    # seule) le marque \Seen, comme le ferait un vrai serveur -- et le fait
    # migrer new/ -> cur/. Un simple FETCH FLAGS/UID ne compte pas comme une
    # "lecture" du contenu.
    body_was_read = "BODY[HEADER]" in data_items or "BODY[]" in data_items
    if body_was_read and not session.readonly:
        session.backend.set_flags(
            session.username,
            message.uid,
            {Flag.SEEN},
            mailbox=session.selected_mailbox,
            mode="add",
        )

    lines.append(f"{tag} OK FETCH completed")
    return lines


def handle_store(session, tag, args):
    err = _require_selected(session, tag)
    if err:
        return err
    if len(args) < 3:
        return [f"{tag} BAD STORE requires a message number, a mode, and flags"]

    try:
        seq_num = int(args[0])
    except ValueError:
        return [f"{tag} BAD Invalid message number"]

    mode_token = args[1].upper()
    mode_map = {"FLAGS": "replace", "+FLAGS": "add", "-FLAGS": "remove"}
    if mode_token not in mode_map:
        return [f"{tag} BAD Invalid STORE mode"]

    messages = session.backend.list_messages(session.username, session.selected_mailbox)
    if seq_num < 1 or seq_num > len(messages):
        return [f"{tag} NO No such message"]
    message = messages[seq_num - 1]

    flags = _parse_flag_list(args[2:])
    updated = session.backend.set_flags(
        session.username,
        message.uid,
        flags,
        mailbox=session.selected_mailbox,
        mode=mode_map[mode_token],
    )

    return [
        f"* {seq_num} FETCH (FLAGS ({' '.join(updated.flags_imap())}))",
        f"{tag} OK STORE completed",
    ]


def handle_search(session, tag, args):
    err = _require_selected(session, tag)
    if err:
        return err

    criteria = [a.upper() for a in args] if args else ["ALL"]
    criterion = criteria[0]
    messages = session.backend.list_messages(
        session.username, session.selected_mailbox, include_raw=True
    )

    matches = []
    for seq_num, message in enumerate(messages, start=1):
        if criterion == "ALL":
            matches.append(seq_num)
        elif criterion == "UNSEEN":
            if Flag.SEEN not in message.flags:
                matches.append(seq_num)
        elif criterion == "FROM" and len(criteria) > 1:
            needle = args[1].strip('"').lower()
            header = _extract_header(message.raw).decode("utf-8", errors="replace").lower()
            if "from:" in header and needle in header:
                matches.append(seq_num)

    return [
        ("* SEARCH " + " ".join(str(n) for n in matches)).rstrip(),
        f"{tag} OK SEARCH completed",
    ]


def handle_expunge(session, tag, args):
    err = _require_selected(session, tag)
    if err:
        return err

    # Limitation assumée : on annonce les UID supprimés plutôt que les
    # sequence numbers "live" (ce qui nécessiterait de rejouer la suppression
    # message par message en renumérotant à chaque suppression, comme le
    # ferait un serveur RFC-strict).
    removed_uids = session.backend.expunge(session.username, session.selected_mailbox)
    lines = [f"* {uid} EXPUNGE" for uid in removed_uids]
    lines.append(f"{tag} OK EXPUNGE completed")
    return lines


def handle_uid(session, tag, args):
    """
    UID est un PRÉFIXE de commande en IMAP, pas une commande en soi :
    'UID FETCH ...', 'UID STORE ...', 'UID SEARCH ...'. Les numéros de
    message passés en argument désignent alors des UID (stables) et non
    des numéros de séquence (qui changent après un EXPUNGE).

    ⚠️ C'est cette commande qui manquait et empêchait des clients réels
    comme Thunderbird d'afficher le moindre message : ils utilisent presque
    systématiquement 'UID FETCH 1:* (FLAGS)' pour synchroniser leur cache
    local juste après un SELECT.
    """
    if not args:
        return [f"{tag} BAD UID requires a subcommand (FETCH/STORE/SEARCH)"]

    subcommand = args[0].upper()
    rest = args[1:]

    if subcommand == "FETCH":
        return _uid_fetch(session, tag, rest)
    if subcommand == "STORE":
        return _uid_store(session, tag, rest)
    if subcommand == "SEARCH":
        return _uid_search(session, tag, rest)

    return [f"{tag} BAD Unsupported UID subcommand: {subcommand}"]


def _uid_fetch(session, tag, args):
    err = _require_selected(session, tag)
    if err:
        return err
    if len(args) < 2:
        return [f"{tag} BAD UID FETCH requires a uid-set and data items"]

    uid_set_token = args[0]
    data_items = " ".join(args[1:]).upper()

    messages = session.backend.list_messages(
        session.username, session.selected_mailbox, include_raw=True
    )
    existing_uids = [m.uid for m in messages]

    try:
        target_uids = _expand_uid_set(uid_set_token, existing_uids)
    except ValueError:
        return [f"{tag} BAD Invalid uid-set"]

    body_was_read = "BODY[HEADER]" in data_items or "BODY[]" in data_items
    lines = []

    for seq_num, message in enumerate(messages, start=1):
        if message.uid not in target_uids:
            continue

        # En UID FETCH, le UID doit TOUJOURS figurer dans la réponse, même
        # si le client ne l'a pas explicitement demandé (RFC 3501 §6.4.8).
        parts = [f"UID {message.uid}"]
        if "FLAGS" in data_items:
            parts.append(f"FLAGS ({' '.join(message.flags_imap())})")
        if "BODY[HEADER]" in data_items:
            header = _extract_header(message.raw)
            text = header.decode("utf-8", errors="replace")
            parts.append(f"BODY[HEADER] {{{len(header)}}}\r\n{text}")
        elif "BODY[]" in data_items:
            text = message.raw.decode("utf-8", errors="replace")
            parts.append(f"BODY[] {{{len(message.raw)}}}\r\n{text}")

        lines.append(f"* {seq_num} FETCH ({' '.join(parts)})")

        if body_was_read and not session.readonly:
            session.backend.set_flags(
                session.username,
                message.uid,
                {Flag.SEEN},
                mailbox=session.selected_mailbox,
                mode="add",
            )

    lines.append(f"{tag} OK UID FETCH completed")
    return lines


def _uid_store(session, tag, args):
    err = _require_selected(session, tag)
    if err:
        return err
    if len(args) < 3:
        return [f"{tag} BAD UID STORE requires a uid-set, a mode, and flags"]

    uid_set_token = args[0]
    mode_token = args[1].upper()
    mode_map = {"FLAGS": "replace", "+FLAGS": "add", "-FLAGS": "remove"}
    if mode_token not in mode_map:
        return [f"{tag} BAD Invalid STORE mode"]

    flags = _parse_flag_list(args[2:])
    messages = session.backend.list_messages(session.username, session.selected_mailbox)
    existing_uids = [m.uid for m in messages]

    try:
        target_uids = _expand_uid_set(uid_set_token, existing_uids)
    except ValueError:
        return [f"{tag} BAD Invalid uid-set"]

    lines = []
    for seq_num, message in enumerate(messages, start=1):
        if message.uid not in target_uids:
            continue
        updated = session.backend.set_flags(
            session.username,
            message.uid,
            flags,
            mailbox=session.selected_mailbox,
            mode=mode_map[mode_token],
        )
        lines.append(f"* {seq_num} FETCH (FLAGS ({' '.join(updated.flags_imap())}) UID {message.uid})")

    lines.append(f"{tag} OK UID STORE completed")
    return lines


def _uid_search(session, tag, args):
    err = _require_selected(session, tag)
    if err:
        return err

    criteria = [a.upper() for a in args] if args else ["ALL"]
    criterion = criteria[0]
    messages = session.backend.list_messages(
        session.username, session.selected_mailbox, include_raw=True
    )

    matches = []
    for message in messages:
        if criterion == "ALL":
            matches.append(message.uid)
        elif criterion == "UNSEEN":
            if Flag.SEEN not in message.flags:
                matches.append(message.uid)
        elif criterion == "FROM" and len(criteria) > 1:
            needle = args[1].strip('"').lower()
            header = _extract_header(message.raw).decode("utf-8", errors="replace").lower()
            if "from:" in header and needle in header:
                matches.append(message.uid)

    return [
        ("* SEARCH " + " ".join(str(u) for u in matches)).rstrip(),
        f"{tag} OK UID SEARCH completed",
    ]