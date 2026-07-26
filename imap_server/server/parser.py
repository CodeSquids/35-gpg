"""
Parseur du sous-ensemble IMAP4rev1 supporté.

Une ligne de commande IMAP a la forme :
    <tag> <commande> [arguments...]

Les arguments peuvent être des atomes nus (LOGIN testuser) ou des chaînes
entre guillemets (LOGIN "test user" "pass word"), qui peuvent contenir des
espaces. On ne gère pas les "literals" (`{n}\r\n...`) de la RFC complète :
c'est une limitation assumée, cohérente avec le sous-ensemble déjà annoncé
dans le README d'origine.
"""

from __future__ import annotations

from dataclasses import dataclass


class ParseError(Exception):
    """Levée quand une ligne ne peut pas être découpée en commande valide."""


@dataclass
class ParsedCommand:
    tag: str
    name: str  # nom de commande, toujours en MAJUSCULES
    args: list[str]


def parse_line(line: str) -> ParsedCommand:
    line = line.rstrip("\r\n")
    if not line.strip():
        raise ParseError("Ligne vide")

    tokens = _tokenize(line)
    if len(tokens) < 2:
        raise ParseError("Commande incomplète : tag et nom de commande requis")

    tag, name, *args = tokens
    return ParsedCommand(tag=tag, name=name.upper(), args=args)


def _tokenize(line: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    n = len(line)

    while i < n:
        while i < n and line[i] == " ":
            i += 1
        if i >= n:
            break

        if line[i] == '"':
            j = i + 1
            buf: list[str] = []
            while j < n and line[j] != '"':
                if line[j] == "\\" and j + 1 < n:
                    buf.append(line[j + 1])
                    j += 2
                else:
                    buf.append(line[j])
                    j += 1
            if j >= n:
                raise ParseError("Chaîne entre guillemets non terminée")
            tokens.append("".join(buf))
            i = j + 1
        else:
            j = i
            while j < n and line[j] != " ":
                j += 1
            tokens.append(line[i:j])
            i = j

    return tokens