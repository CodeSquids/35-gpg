import os
import shutil
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from accounts import AccountStore
from storage import MaildirBackend
from imap_server.server.session import ImapSession
from imap_server.server.session_state import SessionState


@pytest.fixture
def env():
    tmp_dir = tempfile.mkdtemp()
    account_store = AccountStore(data_dir=tmp_dir)
    backend = MaildirBackend(data_dir=tmp_dir)
    account_store.create_account("andria", "hunter2")
    yield account_store, backend
    shutil.rmtree(tmp_dir, ignore_errors=True)


def _session(env) -> ImapSession:
    account_store, backend = env
    return ImapSession(account_store=account_store, backend=backend)


# -- Reproduction exacte du bug d'origine ------------------------------------

def test_capability_then_login_then_select_sequence_works(env):
    """
    Reproduit le scénario exact rapporté : CAPABILITY, puis LOGIN, puis
    SELECT à la suite -- qui échouait avant la correction de la state
    machine ("Cannot LOGIN in current state" / "Please authenticate first").
    """
    session = _session(env)

    cap_resp = session.handle_command("a001", "CAPABILITY", [])
    assert any("OK CAPABILITY completed" in line for line in cap_resp)
    assert session.state == SessionState.NOT_AUTHENTICATED  # inchangé !

    login_resp = session.handle_command("a002", "LOGIN", ["andria", "hunter2"])
    assert any("OK LOGIN completed" in line for line in login_resp)
    assert session.state == SessionState.AUTHENTICATED

    select_resp = session.handle_command("a003", "SELECT", ["INBOX"])
    assert any("OK [READ-WRITE] SELECT completed" in line for line in select_resp)
    assert session.state == SessionState.SELECTED


def test_capability_does_not_change_state(env):
    session = _session(env)
    for _ in range(3):
        session.handle_command("a", "CAPABILITY", [])
    assert session.state == SessionState.NOT_AUTHENTICATED


# -- LOGIN / LOGOUT ------------------------------------------------------------

def test_login_wrong_password_stays_not_authenticated(env):
    session = _session(env)
    resp = session.handle_command("a001", "LOGIN", ["andria", "wrongpass"])
    assert any("NO LOGIN failed" in line for line in resp)
    assert session.state == SessionState.NOT_AUTHENTICATED


def test_login_twice_rejected(env):
    session = _session(env)
    session.handle_command("a001", "LOGIN", ["andria", "hunter2"])
    resp = session.handle_command("a002", "LOGIN", ["andria", "hunter2"])
    assert any("NO Cannot LOGIN in current state" in line for line in resp)


def test_logout_from_any_state(env):
    session = _session(env)
    session.handle_command("a001", "LOGIN", ["andria", "hunter2"])
    resp = session.handle_command("a002", "LOGOUT", [])
    assert any("BYE LOGOUT requested" in line for line in resp)
    assert any("OK LOGOUT completed" in line for line in resp)
    assert session.state == SessionState.LOGOUT


# -- REGISTER --------------------------------------------------------------------

def test_register_creates_account_and_allows_login(env):
    session = _session(env)
    resp = session.handle_command("a001", "REGISTER", ["nouvel_user", "motdepasse"])
    assert any("OK REGISTER completed" in line for line in resp)

    login_resp = session.handle_command("a002", "LOGIN", ["nouvel_user", "motdepasse"])
    assert any("OK LOGIN completed" in line for line in login_resp)


def test_register_duplicate_username_rejected(env):
    session = _session(env)
    resp = session.handle_command("a001", "REGISTER", ["andria", "autrepass"])
    assert any(line.startswith("a001 NO") for line in resp)


def test_register_rejected_once_authenticated(env):
    session = _session(env)
    session.handle_command("a001", "LOGIN", ["andria", "hunter2"])
    resp = session.handle_command("a002", "REGISTER", ["autre", "pass"])
    assert any("NO Cannot REGISTER in current state" in line for line in resp)


# -- SELECT / accès non authentifié ------------------------------------------------

def test_select_before_login_rejected(env):
    session = _session(env)
    resp = session.handle_command("a001", "SELECT", ["INBOX"])
    assert any("NO Please authenticate first" in line for line in resp)
    assert session.state == SessionState.NOT_AUTHENTICATED


def test_fetch_before_select_rejected(env):
    session = _session(env)
    session.handle_command("a001", "LOGIN", ["andria", "hunter2"])
    resp = session.handle_command("a002", "FETCH", ["1", "FLAGS"])
    assert any("NO Please select a mailbox first" in line for line in resp)


# -- FETCH / STORE / SEARCH / EXPUNGE end-to-end -----------------------------------

def test_fetch_flags_and_body(env):
    account_store, backend = env
    backend.deliver_message("andria", b"From: bob\r\nSubject: Salut\r\n\r\nCoucou !")

    session = _session(env)
    session.handle_command("a001", "LOGIN", ["andria", "hunter2"])
    session.handle_command("a002", "SELECT", ["INBOX"])

    resp = session.handle_command("a003", "FETCH", ["1", "FLAGS"])
    assert any("FLAGS ()" in line for line in resp)  # pas encore vu

    resp = session.handle_command("a004", "FETCH", ["1", "BODY[]"])
    assert any("Coucou !" in line for line in resp)

    # Après lecture du corps, le message doit être marqué \Seen
    resp = session.handle_command("a005", "FETCH", ["1", "FLAGS"])
    assert any("\\Seen" in line for line in resp)


def test_store_flags(env):
    account_store, backend = env
    backend.deliver_message("andria", b"body")

    session = _session(env)
    session.handle_command("a001", "LOGIN", ["andria", "hunter2"])
    session.handle_command("a002", "SELECT", ["INBOX"])

    resp = session.handle_command("a003", "STORE", ["1", "+FLAGS", "(\\Flagged)"])
    assert any("\\Flagged" in line for line in resp)
    assert any("OK STORE completed" in line for line in resp)


def test_search_unseen(env):
    account_store, backend = env
    backend.deliver_message("andria", b"first")
    backend.deliver_message("andria", b"second")

    session = _session(env)
    session.handle_command("a001", "LOGIN", ["andria", "hunter2"])
    session.handle_command("a002", "SELECT", ["INBOX"])
    session.handle_command("a003", "STORE", ["1", "+FLAGS", "(\\Seen)"])

    resp = session.handle_command("a004", "SEARCH", ["UNSEEN"])
    assert any(line == "* SEARCH 2" for line in resp)


def test_expunge_removes_deleted_message(env):
    account_store, backend = env
    backend.deliver_message("andria", b"keep")
    backend.deliver_message("andria", b"delete me")

    session = _session(env)
    session.handle_command("a001", "LOGIN", ["andria", "hunter2"])
    session.handle_command("a002", "SELECT", ["INBOX"])
    session.handle_command("a003", "STORE", ["2", "+FLAGS", "(\\Deleted)"])
    resp = session.handle_command("a004", "EXPUNGE", [])

    assert any("EXPUNGE" in line for line in resp if line.startswith("*"))
    assert any("OK EXPUNGE completed" in line for line in resp)

    remaining = backend.list_messages("andria")
    assert len(remaining) == 1


def test_examine_is_read_only(env):
    account_store, backend = env
    backend.deliver_message("andria", b"body")

    session = _session(env)
    session.handle_command("a001", "LOGIN", ["andria", "hunter2"])
    session.handle_command("a002", "EXAMINE", ["INBOX"])
    session.handle_command("a003", "FETCH", ["1", "BODY[]"])

    # En EXAMINE (lecture seule), le message ne doit PAS passer \Seen
    message = backend.get_message("andria", uid=1)
    assert message.flags == set()


def test_select_inbox_is_case_insensitive(env):
    """Reproduit le scenario reporte : select 'inbox' en minuscule doit voir
    les messages livres sur 'INBOX', pas une boite vide separee."""
    account_store, backend = env
    backend.deliver_message("andria", b"body")

    session = _session(env)
    session.handle_command("a001", "LOGIN", ["andria", "hunter2"])
    resp = session.handle_command("a002", "SELECT", ["inbox"])
    assert any("1 EXISTS" in line for line in resp)