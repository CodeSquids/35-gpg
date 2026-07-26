import asyncio
import os
import shutil
import ssl
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import create_tls_context, load_config
from imap_server.server import tcp_server as imap_tcp_server
from smtp_server.server import tcp_server as smtp_tcp_server


@pytest.fixture
def certificate(tmp_path):
    if shutil.which("openssl") is None:
        pytest.skip("openssl est nécessaire pour le test TLS")

    cert_file = tmp_path / "server-cert.pem"
    key_file = tmp_path / "server-key.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-sha256",
            "-nodes",
            "-days",
            "1",
            "-keyout",
            str(key_file),
            "-out",
            str(cert_file),
            "-subj",
            "/CN=localhost",
        ],
        check=True,
        capture_output=True,
    )
    return cert_file, key_file


def test_tls_requires_both_certificate_and_key(monkeypatch):
    monkeypatch.setenv("MAIL_TLS_CERT_FILE", "cert.pem")
    monkeypatch.delenv("MAIL_TLS_KEY_FILE", raising=False)

    with pytest.raises(ValueError, match="TLS requiert"):
        load_config("imap", [])


def test_tls_context_is_optional_and_loads_certificate(certificate):
    cert_file, key_file = certificate
    plain_config = load_config("imap", [])
    tls_config = load_config(
        "imap", ["--tls-cert-file", str(cert_file), "--tls-key-file", str(key_file)]
    )

    assert create_tls_context(plain_config) is None
    assert isinstance(create_tls_context(tls_config), ssl.SSLContext)


@pytest.mark.parametrize(
    "server_module",
    [
        imap_tcp_server,
        smtp_tcp_server,
    ],
)
def test_servers_pass_tls_context_to_asyncio(certificate, tmp_path, monkeypatch, server_module):
    cert_file, key_file = certificate
    config = load_config(
        "imap", ["--tls-cert-file", str(cert_file), "--tls-key-file", str(key_file)]
    )
    server_context = create_tls_context(config)
    captured = {}

    async def fake_start_server(handler, host, port, *, ssl=None):
        captured.update(handler=handler, host=host, port=port, ssl=ssl)
        return object()

    monkeypatch.setattr(server_module.asyncio, "start_server", fake_start_server)
    result = asyncio.run(
        server_module.create_server("127.0.0.1", 993, str(tmp_path), server_context)
    )

    assert result is not None
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 993
    assert captured["ssl"] is server_context
