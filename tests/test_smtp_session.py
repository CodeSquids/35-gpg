import os
import shutil
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from accounts import AccountStore
from storage import MaildirBackend
from smtp_server.server.session import SmtpSession
from smtp_server.server.session_state import SmtpState


@pytest.fixture
def env():
    tmp_dir = tempfile.mkdtemp()
    account_store = AccountStore(data_dir=tmp_dir)
    backend = MaildirBackend(data_dir=tmp_dir)
    account_store.create_account("alice", "pw1")
    account_store.create_account("bob", "pw2")
    yield account_store, backend
    shutil.rmtree(tmp_dir, ignore_errors=True)


def _session(env) -> SmtpSession:
    account_store, backend = env
    return SmtpSession(account_store=account_store, backend=backend)


# -- Cycle complet HELO -> MAIL -> RCPT -> DATA --------------------------------

def test_full_local_delivery_cycle(env):
    account_store, backend = env
    session = _session(env)

    resp = session.handle_command("HELO", "client.local")
    assert any("250" in line for line in resp)
    assert session.state == SmtpState.GREETED

    resp = session.handle_command("MAIL", "FROM:<alice>")
    assert any("250 OK" in line for line in resp)
    assert session.state == SmtpState.MAIL_FROM_SET

    resp = session.handle_command("RCPT", "TO:<bob>")
    assert any("250 OK" in line for line in resp)
    assert session.state == SmtpState.RCPT_SET

    resp = session.handle_command("DATA", "")
    assert any("354" in line for line in resp)
    assert session.in_data_mode is True

    raw = b"Subject: Salut\r\n\r\nComment ca va ?"
    resp = session.finish_data(raw)
    assert any("250 OK" in line and "1 recipient" in line for line in resp)
    assert session.state == SmtpState.GREETED  # retour a l'etat pret
    assert session.in_data_mode is False

    messages = backend.list_messages("bob", include_raw=True)
    assert len(messages) == 1
    assert messages[0].raw == raw


def test_delivery_with_at_domain_addresses(env):
    """Les adresses avec '@domaine' doivent fonctionner : seule la partie
    locale (avant le '@') est utilisee pour la livraison locale."""
    account_store, backend = env
    session = _session(env)

    session.handle_command("HELO", "client.local")
    session.handle_command("MAIL", "FROM:<alice@eni.mg>")
    session.handle_command("RCPT", "TO:<bob@eni.mg>")
    session.handle_command("DATA", "")
    session.finish_data(b"corps du message")

    messages = backend.list_messages("bob", include_raw=True)
    assert len(messages) == 1


def test_multiple_recipients(env):
    account_store, backend = env
    account_store.create_account("carol", "pw3")
    session = _session(env)

    session.handle_command("HELO", "client.local")
    session.handle_command("MAIL", "FROM:<alice>")
    session.handle_command("RCPT", "TO:<bob>")
    session.handle_command("RCPT", "TO:<carol>")
    session.handle_command("DATA", "")
    resp = session.finish_data(b"message pour plusieurs destinataires")

    assert any("2 recipient" in line for line in resp)
    assert len(backend.list_messages("bob")) == 1
    assert len(backend.list_messages("carol")) == 1


# -- Erreurs de sequence -----------------------------------------------------------

def test_mail_before_helo_rejected(env):
    session = _session(env)
    resp = session.handle_command("MAIL", "FROM:<alice>")
    assert any("503" in line for line in resp)


def test_rcpt_before_mail_rejected(env):
    session = _session(env)
    session.handle_command("HELO", "client.local")
    resp = session.handle_command("RCPT", "TO:<bob>")
    assert any("503" in line for line in resp)


def test_data_before_rcpt_rejected(env):
    session = _session(env)
    session.handle_command("HELO", "client.local")
    session.handle_command("MAIL", "FROM:<alice>")
    resp = session.handle_command("DATA", "")
    assert any("503" in line for line in resp)
    assert session.in_data_mode is False


# -- Utilisateurs inconnus (livraison locale uniquement) -----------------------------

def test_mail_from_unknown_user_rejected(env):
    session = _session(env)
    session.handle_command("HELO", "client.local")
    resp = session.handle_command("MAIL", "FROM:<ghost>")
    assert any("550" in line for line in resp)
    assert session.state == SmtpState.GREETED  # pas de transition


def test_rcpt_to_unknown_user_rejected(env):
    session = _session(env)
    session.handle_command("HELO", "client.local")
    session.handle_command("MAIL", "FROM:<alice>")
    resp = session.handle_command("RCPT", "TO:<ghost>")
    assert any("550" in line for line in resp)


# -- RSET / QUIT / NOOP ------------------------------------------------------------

def test_rset_clears_transaction(env):
    session = _session(env)
    session.handle_command("HELO", "client.local")
    session.handle_command("MAIL", "FROM:<alice>")
    session.handle_command("RCPT", "TO:<bob>")

    resp = session.handle_command("RSET", "")
    assert any("250" in line for line in resp)
    assert session.mail_from is None
    assert session.rcpt_to == []
    assert session.state == SmtpState.GREETED


def test_quit_sets_state(env):
    session = _session(env)
    resp = session.handle_command("QUIT", "")
    assert any("221" in line for line in resp)
    assert session.state == SmtpState.QUIT


def test_noop(env):
    session = _session(env)
    resp = session.handle_command("NOOP", "")
    assert any("250" in line for line in resp)


def test_unknown_command(env):
    session = _session(env)
    resp = session.handle_command("FOOBAR", "")
    assert any("502" in line for line in resp)