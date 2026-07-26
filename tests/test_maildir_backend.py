import os
import shutil
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage import Flag, MaildirBackend, NoSuchMessageError


@pytest.fixture
def backend():
    tmp_dir = tempfile.mkdtemp()
    yield MaildirBackend(data_dir=tmp_dir)
    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_ensure_mailbox_creates_structure(backend):
    backend.ensure_mailbox("alice", "INBOX")
    base = backend._mailbox_dir("alice", "INBOX")
    assert os.path.isdir(os.path.join(base, "tmp"))
    assert os.path.isdir(os.path.join(base, "new"))
    assert os.path.isdir(os.path.join(base, "cur"))
    assert os.path.exists(os.path.join(base, "uidlist.json"))


def test_deliver_message_creates_file_in_new(backend):
    uid = backend.deliver_message("alice", b"Subject: Hello\r\n\r\nHi there.")
    base = backend._mailbox_dir("alice", "INBOX")
    new_files = os.listdir(os.path.join(base, "new"))
    assert len(new_files) == 1
    assert uid == 1


def test_deliver_message_no_leftover_tmp_files(backend):
    backend.deliver_message("alice", b"body1")
    backend.deliver_message("alice", b"body2")
    base = backend._mailbox_dir("alice", "INBOX")
    tmp_files = os.listdir(os.path.join(base, "tmp"))
    assert tmp_files == []  # rien ne doit rester dans tmp/ après livraison


def test_uids_increment_and_are_stable(backend):
    uid1 = backend.deliver_message("alice", b"first")
    uid2 = backend.deliver_message("alice", b"second")
    uid3 = backend.deliver_message("alice", b"third")
    assert [uid1, uid2, uid3] == [1, 2, 3]


def test_list_messages_returns_sorted_by_uid(backend):
    backend.deliver_message("alice", b"first")
    backend.deliver_message("alice", b"second")
    messages = backend.list_messages("alice")
    assert [m.uid for m in messages] == [1, 2]
    assert all(m.flags == set() for m in messages)  # nouveaux messages: pas de flag


def test_get_message_returns_raw_content(backend):
    uid = backend.deliver_message("alice", b"Subject: Test\r\n\r\nCorps du message.")
    message = backend.get_message("alice", uid)
    assert message.raw == b"Subject: Test\r\n\r\nCorps du message."


def test_get_message_unknown_uid_raises(backend):
    with pytest.raises(NoSuchMessageError):
        backend.get_message("alice", 999)


def test_set_flags_moves_message_from_new_to_cur(backend):
    uid = backend.deliver_message("alice", b"body")
    base = backend._mailbox_dir("alice", "INBOX")

    backend.set_flags("alice", uid, {Flag.SEEN})

    assert os.listdir(os.path.join(base, "new")) == []
    cur_files = os.listdir(os.path.join(base, "cur"))
    assert len(cur_files) == 1
    assert cur_files[0].endswith(":2,S")


def test_set_flags_replace_mode(backend):
    uid = backend.deliver_message("alice", b"body")
    backend.set_flags("alice", uid, {Flag.SEEN, Flag.FLAGGED})
    message = backend.get_message("alice", uid)
    assert message.flags == {Flag.SEEN, Flag.FLAGGED}

    backend.set_flags("alice", uid, {Flag.ANSWERED}, mode="replace")
    message = backend.get_message("alice", uid)
    assert message.flags == {Flag.ANSWERED}


def test_set_flags_add_mode(backend):
    uid = backend.deliver_message("alice", b"body")
    backend.set_flags("alice", uid, {Flag.SEEN})
    backend.set_flags("alice", uid, {Flag.FLAGGED}, mode="add")
    message = backend.get_message("alice", uid)
    assert message.flags == {Flag.SEEN, Flag.FLAGGED}


def test_set_flags_remove_mode(backend):
    uid = backend.deliver_message("alice", b"body")
    backend.set_flags("alice", uid, {Flag.SEEN, Flag.FLAGGED})
    backend.set_flags("alice", uid, {Flag.FLAGGED}, mode="remove")
    message = backend.get_message("alice", uid)
    assert message.flags == {Flag.SEEN}


def test_set_flags_unknown_uid_raises(backend):
    with pytest.raises(NoSuchMessageError):
        backend.set_flags("alice", 999, {Flag.SEEN})


def test_expunge_removes_deleted_messages(backend):
    uid1 = backend.deliver_message("alice", b"keep me")
    uid2 = backend.deliver_message("alice", b"delete me")

    backend.set_flags("alice", uid2, {Flag.DELETED})
    removed = backend.expunge("alice")

    assert removed == [uid2]
    remaining = backend.list_messages("alice")
    assert [m.uid for m in remaining] == [uid1]


def test_expunge_keeps_non_deleted_messages(backend):
    uid = backend.deliver_message("alice", b"keep me")
    backend.set_flags("alice", uid, {Flag.SEEN})
    removed = backend.expunge("alice")
    assert removed == []
    assert len(backend.list_messages("alice")) == 1


def test_mailboxes_are_isolated_per_user(backend):
    backend.deliver_message("alice", b"for alice")
    backend.deliver_message("bob", b"for bob")

    alice_messages = backend.list_messages("alice", include_raw=True)
    bob_messages = backend.list_messages("bob", include_raw=True)

    assert len(alice_messages) == 1
    assert len(bob_messages) == 1
    assert alice_messages[0].raw == b"for alice"
    assert bob_messages[0].raw == b"for bob"


def test_uidvalidity_is_stable_across_backend_instances():
    tmp_dir = tempfile.mkdtemp()
    try:
        backend1 = MaildirBackend(data_dir=tmp_dir)
        backend1.ensure_mailbox("alice")
        validity1 = backend1.get_uidvalidity("alice")

        backend2 = MaildirBackend(data_dir=tmp_dir)
        validity2 = backend2.get_uidvalidity("alice")

        assert validity1 == validity2
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_list_mailboxes(backend):
    backend.ensure_mailbox("alice", "INBOX")
    backend.ensure_mailbox("alice", "Sent")
    assert backend.list_mailboxes("alice") == ["INBOX", "Sent"]