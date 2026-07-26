"""
Commandes du sous-ensemble SMTP implémenté.

⚠️ Limitation assumée (cf. ROADMAP.md, Étape 0.1) : ce serveur ne fait QUE
de la livraison locale. `MAIL FROM` et `RCPT TO` sont acceptés seulement si
la partie locale de l'adresse (avant le "@", ou l'adresse entière si pas de
"@") correspond à un compte existant sur CE serveur. Il n'y a pas de relais
vers d'autres serveurs, pas de DNS/MX, pas de file d'attente.

Autre limitation assumée : pas d'authentification SMTP (AUTH) pour cette
première version -- on vérifie seulement que l'expéditeur déclaré existe
en tant que compte local. Ajouter une vraie AUTH (LOGIN/PLAIN) est une
extension naturelle mais hors scope de cette étape.
"""

from __future__ import annotations

import re

from ..server.session_state import SmtpState

_ADDR_RE = re.compile(r"<([^>]*)>")


def _extract_address(arg: str) -> str | None:
    match = _ADDR_RE.search(arg)
    if match:
        return match.group(1).strip() or None
    # Tolère aussi une adresse sans chevrons (certains clients simplistes)
    candidate = arg.strip()
    return candidate or None


def _local_part(address: str) -> str:
    return address.split("@", 1)[0]


def handle_helo(session, arg: str) -> list[str]:
    if not arg:
        return ["501 Syntax: HELO hostname"]
    session.client_hostname = arg
    session.state = SmtpState.GREETED
    return [f"250 Hello {arg}"]


def handle_mail(session, arg: str) -> list[str]:
    if session.state == SmtpState.INIT:
        return ["503 Bad sequence of commands: send HELO first"]
    if not arg.upper().startswith("FROM:"):
        return ["501 Syntax: MAIL FROM:<address>"]

    address = _extract_address(arg[len("FROM:"):])
    if not address:
        return ["501 Syntax: MAIL FROM:<address>"]

    username = _local_part(address)
    if not session.account_store.account_exists(username):
        return [f"550 No such local user: {username}"]

    session.mail_from = address
    session.rcpt_to = []
    session.state = SmtpState.MAIL_FROM_SET
    return ["250 OK"]


def handle_rcpt(session, arg: str) -> list[str]:
    if session.state not in (SmtpState.MAIL_FROM_SET, SmtpState.RCPT_SET):
        return ["503 Bad sequence of commands: send MAIL FROM first"]
    if not arg.upper().startswith("TO:"):
        return ["501 Syntax: RCPT TO:<address>"]

    address = _extract_address(arg[len("TO:"):])
    if not address:
        return ["501 Syntax: RCPT TO:<address>"]

    username = _local_part(address)
    if not session.account_store.account_exists(username):
        return [f"550 No such local user: {username}"]

    session.rcpt_to.append(address)
    session.state = SmtpState.RCPT_SET
    return ["250 OK"]


def handle_data_start(session) -> tuple[list[str], bool]:
    """Retourne (lignes_de_reponse, doit_entrer_en_mode_donnees)."""
    if session.state != SmtpState.RCPT_SET:
        return (
            ["503 Bad sequence of commands: need MAIL FROM and at least one RCPT TO first"],
            False,
        )
    return (["354 Start mail input; end with <CRLF>.<CRLF>"], True)


def handle_data_end(session, raw_message: bytes) -> list[str]:
    """Livre le message à chaque destinataire déclaré, puis réinitialise
    l'état de la transaction (comme le veut le protocole SMTP après un
    message complet)."""
    delivered_to = []
    for address in session.rcpt_to:
        username = _local_part(address)
        session.backend.deliver_message(username, raw_message)
        delivered_to.append(username)

    session.mail_from = None
    session.rcpt_to = []
    session.state = SmtpState.GREETED

    return [f"250 OK: message delivered to {len(delivered_to)} recipient(s)"]


def handle_rset(session) -> list[str]:
    session.mail_from = None
    session.rcpt_to = []
    if session.state != SmtpState.INIT:
        session.state = SmtpState.GREETED
    return ["250 OK"]


def handle_noop(session) -> list[str]:
    return ["250 OK"]


def handle_quit(session) -> list[str]:
    session.state = SmtpState.QUIT
    return ["221 Bye"]