"""
State machine de la connexion IMAP.

Isolée dans son propre module (plutôt que dans session.py) pour éviter tout
import circulaire avec commands/ : les modules commands/*.py ont besoin de
connaître les états possibles, mais session.py a besoin d'importer les
handlers de commands/*.py. En séparant l'enum, les deux sens d'import
restent propres.

Rappel des 3 états (+ LOGOUT) documentés dans le README d'origine :
    NOT_AUTHENTICATED -> (LOGIN réussi) -> AUTHENTICATED
    AUTHENTICATED      -> (SELECT/EXAMINE) -> SELECTED
    N'importe quel état -> (LOGOUT) -> LOGOUT

Le bug rencontré ("Cannot LOGIN in current state" juste après CAPABILITY)
venait du fait que l'ancienne implémentation ne garantissait pas que
CAPABILITY laisse l'état inchangé, et/ou initialisait mal l'état de
connexion. Ici, l'état initial est fixé explicitement à la construction de
ImapSession (voir session.py), et CAPABILITY ne touche jamais à self.state.
"""

from enum import Enum, auto


class SessionState(Enum):
    NOT_AUTHENTICATED = auto()
    AUTHENTICATED = auto()
    SELECTED = auto()
    LOGOUT = auto()