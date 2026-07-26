import os
import shutil
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from accounts import (
    AccountAlreadyExistsError,
    AccountStore,
    InvalidCredentialsError,
)
from accounts.store import InvalidUsernameError


@pytest.fixture
def store():
    tmp_dir = tempfile.mkdtemp()
    yield AccountStore(data_dir=tmp_dir)
    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_create_account_success(store):
    account = store.create_account("andria", "hunter2")
    assert account.username == "andria"
    assert account.password_hash != "hunter2"  # jamais stocké en clair
    assert store.account_exists("andria")


def test_create_duplicate_account_raises(store):
    store.create_account("andria", "hunter2")
    with pytest.raises(AccountAlreadyExistsError):
        store.create_account("andria", "autremotdepasse")


def test_create_account_invalid_username(store):
    with pytest.raises(InvalidUsernameError):
        store.create_account("ab", "hunter2")  # trop court
    with pytest.raises(InvalidUsernameError):
        store.create_account("user with space", "hunter2")


def test_create_account_empty_password(store):
    with pytest.raises(ValueError):
        store.create_account("andria", "")


def test_verify_password_success(store):
    store.create_account("andria", "hunter2")
    account = store.verify_password("andria", "hunter2")
    assert account.username == "andria"


def test_verify_password_wrong_password(store):
    store.create_account("andria", "hunter2")
    with pytest.raises(InvalidCredentialsError):
        store.verify_password("andria", "wrongpass")


def test_verify_password_unknown_user(store):
    with pytest.raises(InvalidCredentialsError):
        store.verify_password("ghost", "whatever")


def test_list_usernames(store):
    store.create_account("alice", "pw1")
    store.create_account("bob", "pw2")
    assert store.list_usernames() == ["alice", "bob"]


def test_persistence_across_instances():
    tmp_dir = tempfile.mkdtemp()
    try:
        store1 = AccountStore(data_dir=tmp_dir)
        store1.create_account("andria", "hunter2")

        store2 = AccountStore(data_dir=tmp_dir)
        assert store2.account_exists("andria")
        account = store2.verify_password("andria", "hunter2")
        assert account.username == "andria"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)