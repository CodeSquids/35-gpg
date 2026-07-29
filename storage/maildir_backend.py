"""
Backend de stockage Maildir, partagé entre le serveur IMAP (lecture/
modification) et le futur serveur SMTP (livraison).

Convention Maildir (résumé) :
  data/<username>/<mailbox>/
      tmp/   fichiers en cours d'écriture (pas encore visibles des clients)
      new/   messages livrés, pas encore vus par aucun client
      cur/   messages déjà vus au moins une fois par un client ; le nom de
             fichier porte alors un suffixe ":2,<lettres de flags triées>"

Pourquoi tmp/ puis rename() : rename() est atomique sur un même système de
fichiers, donc un client qui liste new/ ou cur/ ne peut jamais tomber sur un
fichier à moitié écrit.

Attribution des UID : Maildir "pur" n'a pas de notion d'UID IMAP. On tient
donc, par mailbox, un petit fichier `uidlist.json` qui fait correspondre
chaque nom de fichier physique à un UID stable, avec un UIDVALIDITY et un
compteur next_uid -- ce qui est l'approche standard (Courier/Dovecot font
la même chose avec leurs propres fichiers d'index).
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from dataclasses import dataclass

from .models import Flag, Message

_HOSTNAME = socket.gethostname().replace("/", "_").replace(":", "_")
_DELIVERY_COUNTER_LOCK = threading.Lock()
_delivery_counter = 0


class NoSuchMessageError(Exception):
    """Levée quand un UID demandé n'existe pas dans la mailbox."""


class NoSuchMailboxError(Exception):
    """Levée quand la mailbox demandée n'existe pas pour cet utilisateur."""


def _unique_maildir_name() -> str:
    """
    Génère un nom de fichier unique conforme à l'esprit de la convention
    Maildir : <horodatage>.M<microsecondes>P<pid>Q<compteur>.<hostname>
    Le compteur protège contre deux livraisons dans le même microseconde
    au sein du même process (rare mais possible avec asyncio).
    """
    global _delivery_counter
    with _DELIVERY_COUNTER_LOCK:
        _delivery_counter += 1
        counter = _delivery_counter
    now = time.time()
    seconds = int(now)
    microseconds = int((now - seconds) * 1_000_000)
    pid = os.getpid()
    return f"{seconds}.M{microseconds}P{pid}Q{counter}.{_HOSTNAME}"


def _encode_flags(flags: set[Flag]) -> str:
    letters = sorted(f.maildir_letter for f in flags)
    return "".join(letters)


def _decode_flags(letters: str) -> set[Flag]:
    result = set()
    for letter in letters:
        try:
            result.add(Flag.from_maildir_letter(letter))
        except ValueError:
            continue  # lettre inconnue -> ignorée plutôt que planter
    return result


def _normalize_mailbox_name(mailbox: str) -> str:
    """
    RFC 3501 impose que le nom de mailbox 'INBOX' soit traité de façon
    insensible à la casse (INBOX, Inbox, inbox... désignent la même boîte).
    Les autres noms de mailbox restent sensibles à la casse (comportement
    standard de la plupart des serveurs IMAP réels).
    """
    if mailbox.strip().upper() == "INBOX":
        return "INBOX"
    return mailbox


def _split_info_suffix(filename: str) -> tuple[str, str]:
    """
    Sépare un nom de fichier Maildir en (base, lettres_de_flags).
    Un fichier dans new/ sans suffixe ":2," renvoie des flags vides.
    """
    marker = ":2,"
    idx = filename.rfind(marker)
    if idx == -1:
        return filename, ""
    return filename[:idx], filename[idx + len(marker):]


@dataclass
class _UidEntry:
    uid: int
    filename: str
    in_new: bool  # True si actuellement dans new/, False si dans cur/


class MaildirBackend:
    """
    API de haut niveau utilisée par les serveurs IMAP et SMTP pour
    manipuler les mailboxes Maildir de tous les utilisateurs.
    """

    def __init__(self, data_dir: str):
        self._data_dir = data_dir
        self._lock = threading.Lock()  # protège les fichiers uidlist.json
        os.makedirs(self._data_dir, exist_ok=True)

    # -- Chemins -----------------------------------------------------------

    def _user_dir(self, username: str) -> str:
        return os.path.join(self._data_dir, username)

    def _mailbox_dir(self, username: str, mailbox: str) -> str:
        mailbox = _normalize_mailbox_name(mailbox)
        return os.path.join(self._user_dir(username), mailbox)

    def _uidlist_path(self, username: str, mailbox: str) -> str:
        return os.path.join(self._mailbox_dir(username, mailbox), "uidlist.json")

    # -- Gestion des mailboxes -----------------------------------------------

    def ensure_mailbox(self, username: str, mailbox: str = "INBOX") -> None:
        """Crée la structure tmp/new/cur (et le uidlist) si elle n'existe pas."""
        base = self._mailbox_dir(username, mailbox)
        for sub in ("tmp", "new", "cur"):
            os.makedirs(os.path.join(base, sub), exist_ok=True)

        uidlist_path = self._uidlist_path(username, mailbox)
        if not os.path.exists(uidlist_path):
            with self._lock:
                if not os.path.exists(uidlist_path):  # revérifie sous verrou
                    self._write_uidlist(
                        username,
                        mailbox,
                        {
                            "uidvalidity": int(time.time()),
                            "next_uid": 1,
                            "map": {},  # filename -> uid
                        },
                    )

    def mailbox_exists(self, username: str, mailbox: str = "INBOX") -> bool:
        return os.path.isdir(self._mailbox_dir(username, mailbox))

    def list_mailboxes(self, username: str) -> list[str]:
        user_dir = self._user_dir(username)
        if not os.path.isdir(user_dir):
            return []
        return sorted(
            name for name in os.listdir(user_dir)
            if os.path.isdir(os.path.join(user_dir, name))
        )

    # -- uidlist.json --------------------------------------------------------

    def _read_uidlist(self, username: str, mailbox: str) -> dict:
        path = self._uidlist_path(username, mailbox)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_uidlist(self, username: str, mailbox: str, data: dict) -> None:
        path = self._uidlist_path(username, mailbox)
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, path)

    def get_uidvalidity(self, username: str, mailbox: str = "INBOX") -> int:
        self.ensure_mailbox(username, mailbox)
        with self._lock:
            return self._read_uidlist(username, mailbox)["uidvalidity"]

    def get_next_uid(self, username: str, mailbox: str = "INBOX") -> int:
        """UID qui sera attribué au PROCHAIN message livré. Utilisé par la
        commande IMAP STATUS (item UIDNEXT)."""
        self.ensure_mailbox(username, mailbox)
        with self._lock:
            return self._read_uidlist(username, mailbox)["next_uid"]

    # -- Livraison (utilisé par SMTP, et par IMAP APPEND) --------------------

    def deliver_message(
        self, username: str, raw_message: bytes, mailbox: str = "INBOX"
    ) -> int:
        """
        Dépose un message dans new/ pour l'utilisateur donné, lui attribue
        un UID, et retourne cet UID.

        Écriture atomique : on écrit dans tmp/ puis on rename() vers new/,
        pour qu'un client IMAP ne puisse jamais voir un fichier incomplet.
        """
        self.ensure_mailbox(username, mailbox)
        base = self._mailbox_dir(username, mailbox)
        filename = _unique_maildir_name()

        tmp_path = os.path.join(base, "tmp", filename)
        new_path = os.path.join(base, "new", filename)

        with open(tmp_path, "wb") as f:
            f.write(raw_message)
            f.flush()
            os.fsync(f.fileno())
        os.rename(tmp_path, new_path)

        with self._lock:
            data = self._read_uidlist(username, mailbox)
            uid = data["next_uid"]
            data["next_uid"] = uid + 1
            data["map"][filename] = uid
            self._write_uidlist(username, mailbox, data)

        return uid

    # -- Listing / lecture ----------------------------------------------------

    def _scan(self, username: str, mailbox: str) -> list[_UidEntry]:
        """Reconstruit la liste des messages présents sur disque avec leur UID,
        en attribuant un UID aux fichiers trouvés qui n'en auraient pas encore
        (cas d'un message déposé manuellement hors de deliver_message)."""
        self.ensure_mailbox(username, mailbox)
        base = self._mailbox_dir(username, mailbox)
        new_dir = os.path.join(base, "new")
        cur_dir = os.path.join(base, "cur")

        with self._lock:
            data = self._read_uidlist(username, mailbox)
            changed = False

            entries: list[_UidEntry] = []
            for in_new, directory in ((True, new_dir), (False, cur_dir)):
                for filename in os.listdir(directory):
                    base_name, _flags = _split_info_suffix(filename)
                    uid = data["map"].get(filename)
                    if uid is None:
                        # Fichier inconnu du uidlist (ex: déposé manuellement) :
                        # on lui attribue un nouvel UID pour rester cohérent.
                        uid = data["next_uid"]
                        data["next_uid"] = uid + 1
                        data["map"][filename] = uid
                        changed = True
                    entries.append(
                        _UidEntry(uid=uid, filename=filename, in_new=in_new)
                    )

            if changed:
                self._write_uidlist(username, mailbox, data)

        entries.sort(key=lambda e: e.uid)
        return entries

    def list_messages(
        self, username: str, mailbox: str = "INBOX", include_raw: bool = False
    ) -> list[Message]:
        """Liste tous les messages (new + cur) triés par UID croissant."""
        base = self._mailbox_dir(username, mailbox)
        result = []
        for entry in self._scan(username, mailbox):
            _base_name, flag_letters = _split_info_suffix(entry.filename)
            flags = _decode_flags(flag_letters)
            raw = None
            if include_raw:
                directory = "new" if entry.in_new else "cur"
                path = os.path.join(base, directory, entry.filename)
                with open(path, "rb") as f:
                    raw = f.read()
            result.append(
                Message(uid=entry.uid, filename=entry.filename, flags=flags, raw=raw)
            )
        return result

    def get_message(
        self, username: str, uid: int, mailbox: str = "INBOX"
    ) -> Message:
        for entry in self._scan(username, mailbox):
            if entry.uid == uid:
                base = self._mailbox_dir(username, mailbox)
                directory = "new" if entry.in_new else "cur"
                path = os.path.join(base, directory, entry.filename)
                with open(path, "rb") as f:
                    raw = f.read()
                _base_name, flag_letters = _split_info_suffix(entry.filename)
                return Message(
                    uid=uid,
                    filename=entry.filename,
                    flags=_decode_flags(flag_letters),
                    raw=raw,
                )
        raise NoSuchMessageError(f"Aucun message avec UID {uid} dans {mailbox}.")

    # -- Modification des flags -----------------------------------------------

    def set_flags(
        self,
        username: str,
        uid: int,
        flags: set[Flag],
        mailbox: str = "INBOX",
        mode: str = "replace",
    ) -> Message:
        """
        Modifie les flags d'un message identifié par son UID.

        mode: "replace" (remplace tout), "add" (ajoute), "remove" (retire).
        Lire un message pour la première fois (n'importe quelle opération
        dessus) le déplace de new/ vers cur/, comme le fait un vrai serveur
        Maildir dès qu'un client a "vu" le message.
        """
        base = self._mailbox_dir(username, mailbox)
        entries = self._scan(username, mailbox)
        target = next((e for e in entries if e.uid == uid), None)
        if target is None:
            raise NoSuchMessageError(f"Aucun message avec UID {uid} dans {mailbox}.")

        _base_name, flag_letters = _split_info_suffix(target.filename)
        current_flags = _decode_flags(flag_letters)

        if mode == "replace":
            new_flags = set(flags)
        elif mode == "add":
            new_flags = current_flags | flags
        elif mode == "remove":
            new_flags = current_flags - flags
        else:
            raise ValueError(f"mode invalide : {mode}")

        base_name, _ = _split_info_suffix(target.filename)
        new_filename = f"{base_name}:2,{_encode_flags(new_flags)}"

        old_dir = "new" if target.in_new else "cur"
        old_path = os.path.join(base, old_dir, target.filename)
        # Tout message dont on touche les flags est considéré comme "vu" :
        # il migre vers cur/, comme le veut la convention Maildir.
        new_path = os.path.join(base, "cur", new_filename)

        os.rename(old_path, new_path)

        with self._lock:
            data = self._read_uidlist(username, mailbox)
            del data["map"][target.filename]
            data["map"][new_filename] = uid
            self._write_uidlist(username, mailbox, data)

        return Message(uid=uid, filename=new_filename, flags=new_flags, raw=None)

    # -- Déplacement ----------------------------------------------------------

    def move_message(
        self,
        username: str,
        uid: int,
        source_mailbox: str = "INBOX",
        destination_mailbox: str = "Trash",
    ) -> int:
        """Déplace un message vers une autre mailbox et retourne son UID de
        destination.

        Les UID IMAP ne sont valables que dans une mailbox : le message reçoit
        donc un nouvel UID dans le dossier cible. Le fichier est d'abord livré
        dans la destination, puis seulement retiré de la source : une erreur
        pendant la copie ne peut ainsi pas faire perdre le message original.
        """
        if _normalize_mailbox_name(source_mailbox) == _normalize_mailbox_name(
            destination_mailbox
        ):
            # Déplacer un message dans son propre dossier est un no-op.
            self.get_message(username, uid, source_mailbox)
            return uid

        message = self.get_message(username, uid, source_mailbox)
        destination_uid = self.deliver_message(
            username, message.raw, destination_mailbox
        )

        # Un message placé dans la corbeille ne doit pas y arriver déjà marqué
        # \Deleted. Les autres flags (notamment \Seen) sont conservés.
        destination_flags = message.flags - {Flag.DELETED}
        if destination_flags:
            self.set_flags(
                username,
                destination_uid,
                destination_flags,
                mailbox=destination_mailbox,
            )

        entries = self._scan(username, source_mailbox)
        target = next((entry for entry in entries if entry.uid == uid), None)
        if target is None:
            raise NoSuchMessageError(
                f"Aucun message avec UID {uid} dans {source_mailbox}."
            )

        base = self._mailbox_dir(username, source_mailbox)
        directory = "new" if target.in_new else "cur"
        os.remove(os.path.join(base, directory, target.filename))
        with self._lock:
            data = self._read_uidlist(username, source_mailbox)
            data["map"].pop(target.filename, None)
            self._write_uidlist(username, source_mailbox, data)

        return destination_uid

    # -- Expunge ---------------------------------------------------------------

    def expunge(self, username: str, mailbox: str = "INBOX") -> list[int]:
        """Supprime définitivement tous les messages marqués \\Deleted.
        Retourne la liste des UID supprimés."""
        base = self._mailbox_dir(username, mailbox)
        removed_uids = []

        entries = self._scan(username, mailbox)
        with self._lock:
            data = self._read_uidlist(username, mailbox)
            for entry in entries:
                _base_name, flag_letters = _split_info_suffix(entry.filename)
                if Flag.DELETED in _decode_flags(flag_letters):
                    directory = "new" if entry.in_new else "cur"
                    path = os.path.join(base, directory, entry.filename)
                    os.remove(path)
                    data["map"].pop(entry.filename, None)
                    removed_uids.append(entry.uid)
            self._write_uidlist(username, mailbox, data)

        return removed_uids
