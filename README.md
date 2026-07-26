```bash
.venv/bin/python -m pytest tests/ -v
```

## TLS pour un réseau VirtualBox

TLS est désactivé par défaut afin de garder les tests locaux simples. Pour
activer le TLS implicite, fournissez un certificat PEM et sa clé privée aux
deux serveurs. Les ports standards sont 993 (IMAPS) et 465 (SMTPS).

Exemple avec un certificat auto-signé pour une VM dont l'IP privée est
`192.168.56.10` :

```bash
mkdir -p certs
openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 365 \
  -keyout certs/server-key.pem -out certs/server-cert.pem \
  -subj "/CN=192.168.56.10" \
  -addext "subjectAltName=IP:192.168.56.10"

MAIL_TLS_CERT_FILE=certs/server-cert.pem \
MAIL_TLS_KEY_FILE=certs/server-key.pem \
python3.13 -m imap_server.main --host 0.0.0.0 --port 993
```

Dans un second terminal :

```bash
MAIL_TLS_CERT_FILE=certs/server-cert.pem \
MAIL_TLS_KEY_FILE=certs/server-key.pem \
python3.13 -m smtp_server.main --host 0.0.0.0 --port 465
```

Dans Thunderbird, choisissez **SSL/TLS** pour IMAP et SMTP. Un certificat
auto-signé doit être accepté une première fois par le client (ou ajouté à ses
autorités de confiance).


## INSTRUCTIONS

TLS implicite est maintenant implémenté pour IMAP et SMTP.

- IMAPS : port `993`
- SMTPS : port `465`
- TLS est activé avec `MAIL_TLS_CERT_FILE` et `MAIL_TLS_KEY_FILE`.
- TLS 1.2 minimum ; un certificat ou une clé manquante produit une erreur explicite.
- Les clés `certs/*.pem` sont ignorées par Git.
- Tests : **69 réussis**.

Les modifications sont dans [config.py](/home/ubundesk/35-gpg/config.py), les serveurs IMAP/SMTP et le guide de démarrage dans [README.md](/home/ubundesk/35-gpg/README.md).

Sur la VM serveur :

```bash
mkdir -p certs
openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 365 \
  -keyout certs/server-key.pem -out certs/server-cert.pem \
  -subj "/CN=VOTRE_IP_VM" \
  -addext "subjectAltName=IP:VOTRE_IP_VM"
```

Puis, dans deux terminaux :

```bash
MAIL_TLS_CERT_FILE=certs/server-cert.pem \
MAIL_TLS_KEY_FILE=certs/server-key.pem \
.venv/bin/python -m imap_server.main --host 0.0.0.0 --port 993
```

```bash
MAIL_TLS_CERT_FILE=certs/server-cert.pem \
MAIL_TLS_KEY_FILE=certs/server-key.pem \
.venv/bin/python -m smtp_server.main --host 0.0.0.0 --port 465
```

Dans Thunderbird, mettez l’IP privée de la VM serveur et sélectionnez **SSL/TLS** pour IMAP et SMTP. Acceptez l’exception de certificat auto-signé lors de la première connexion.
