"""
State machine du sous-ensemble SMTP implémenté (livraison locale uniquement).

Cycle attendu :
    INIT -> (HELO/EHLO) -> GREETED
    GREETED -> (MAIL FROM) -> MAIL_FROM_SET
    MAIL_FROM_SET -> (RCPT TO, répétable) -> RCPT_SET
    RCPT_SET -> (DATA ... <CRLF>.<CRLF>) -> retour à GREETED (message livré)
    N'importe quel état -> (QUIT) -> QUIT

Comme pour le serveur IMAP, cet enum vit dans son propre module pour éviter
tout import circulaire entre session.py et commands/.
"""

from enum import Enum, auto


class SmtpState(Enum):
    INIT = auto()
    GREETED = auto()
    MAIL_FROM_SET = auto()
    RCPT_SET = auto()
    QUIT = auto()