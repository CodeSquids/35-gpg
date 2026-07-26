"""
Stockage et authentification des comptes utilisateurs.

Stockage : un simple fichier JSON (data/accounts.json). Suffisant pour un
projet académique ; pas de dépendance externe (pas de vraie base de données).

Sécurité des mots de passe : PBKDF2-HMAC-SHA256 avec un sel aléatoire par
compte (module `hashlib` de la stdlib, donc aucune dépendance à installer).
On NE stocke JAMAIS le mot de passe en clair.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import threading
from typing import Optional

from .models import Account

_PBKDF2_ITERATIONS = 200_000
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")


class AccountAlreadyExistsError(Exception):
    """Levée quand on tente de créer un compte avec un username déjà pris."""


class InvalidCredentialsError(Exception):
    """Levée quand le username n'existe pas ou le mot de passe est incorrect."""


class InvalidUsernameError(Exception):
    """Levée quand le username ne respecte pas le format autorisé."""


def _hash_password(password: str, salt: bytes) -> str:
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    )
    return derived.hex()


class AccountStore:
    """
    Accès thread-safe au fichier JSON des comptes.

    Un verrou (Lock) protège les lectures/écritures concurrentes, utile
    puisque le serveur IMAP et le serveur SMTP tourneront potentiellement
    en même temps et partageront ce même fichier.
    """

    def __init__(self, data_dir: str):
        self._data_dir = data_dir
        self._accounts_path = os.path.join(data_dir, "accounts.json")
        self._lock = threading.Lock()
        os.makedirs(self._data_dir, exist_ok=True)
        if not os.path.exists(self._accounts_path):
            self._write_all({})

    # -- Bas niveau -------------------------------------------------------

    def _read_all(self) -> dict[str, dict]:
        if not os.path.exists(self._accounts_path):
            return {}
        with open(self._accounts_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {}
            return json.loads(content)

    def _write_all(self, accounts: dict[str, dict]) -> None:
        tmp_path = self._accounts_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(accounts, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, self._accounts_path)

    # -- API publique -------------------------------------------------------

    def account_exists(self, username: str) -> bool:
        with self._lock:
            accounts = self._read_all()
            return username in accounts

    def create_account(self, username: str, password: str) -> Account:
        """
        Crée un nouveau compte.

        Lève InvalidUsernameError si le format du username est invalide.
        Lève AccountAlreadyExistsError si le compte existe déjà.
        """
        if not _USERNAME_RE.match(username):
            raise InvalidUsernameError(
                "Le nom d'utilisateur doit faire 3 à 32 caractères "
                "(lettres, chiffres, '.', '_', '-' uniquement)."
            )
        if not password:
            raise ValueError("Le mot de passe ne peut pas être vide.")

        with self._lock:
            accounts = self._read_all()
            if username in accounts:
                raise AccountAlreadyExistsError(
                    f"Le compte '{username}' existe déjà."
                )

            salt = secrets.token_bytes(16)
            account = Account(
                username=username,
                password_hash=_hash_password(password, salt),
                salt=salt.hex(),
            )
            accounts[username] = account.to_dict()
            self._write_all(accounts)
            return account

    def verify_password(self, username: str, password: str) -> Account:
        """
        Vérifie les identifiants. Retourne l'Account si correct.
        Lève InvalidCredentialsError sinon (username inconnu OU mot de passe
        incorrect -- volontairement le même message pour ne pas révéler
        quels usernames existent).
        """
        with self._lock:
            accounts = self._read_all()
            data = accounts.get(username)
            if data is None:
                raise InvalidCredentialsError("Identifiants invalides.")

            account = Account.from_dict(data)
            salt = bytes.fromhex(account.salt)
            candidate_hash = _hash_password(password, salt)

            # Comparaison en temps constant pour limiter les attaques par
            # mesure de timing.
            if not secrets.compare_digest(candidate_hash, account.password_hash):
                raise InvalidCredentialsError("Identifiants invalides.")

            return account

    def get_account(self, username: str) -> Optional[Account]:
        with self._lock:
            accounts = self._read_all()
            data = accounts.get(username)
            return Account.from_dict(data) if data else None

    def list_usernames(self) -> list[str]:
        with self._lock:
            return sorted(self._read_all().keys())