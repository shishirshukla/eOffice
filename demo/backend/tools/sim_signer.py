"""Simulates the eOffice Signer app using a test certificate (.pem) instead of a token.

Use it to test the backend on any machine, without Windows or an HYP2003 token.
It makes the same three API calls as the real signer.

Usage:
  python tools/sim_signer.py "eoffice-sign://sign?ticket=...&server=..." test-certs/test-recommender.pem
"""

import base64
import json
import sys
import urllib.request
from urllib.parse import parse_qs, urlparse

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.utils import Prehashed

SIGNER_VERSION = "0.1.0"


def call(server: str, path: str, body=None) -> dict:
    req = urllib.request.Request(
        server + path, method="POST" if body is not None else "GET",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "X-eOffice-Signer-Version": SIGNER_VERSION})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"Server error {e.code}: {json.loads(e.read()).get('error')}")


def main() -> None:
    link, pem_path = sys.argv[1], sys.argv[2]
    q = parse_qs(urlparse(link).query)
    ticket, server = q["ticket"][0], q["server"][0]

    pem = open(pem_path, "rb").read()
    key = serialization.load_pem_private_key(pem, None)
    cert = x509.load_pem_x509_certificate(pem)

    info = call(server, f"/api/signer/tickets/{ticket}")
    print(f"Signing slot {info['slot']} ({info['role']}) as {info['name']}: {info['action']}")

    cert_b64 = base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode()
    digest = base64.b64decode(call(server, f"/api/signer/tickets/{ticket}/certificate",
                                   {"certificate": cert_b64})["digest"])
    # Same operation as RSA.SignHash(digest, SHA256, Pkcs1) in the .NET signer.
    sig = key.sign(digest, padding.PKCS1v15(), Prehashed(hashes.SHA256()))
    result = call(server, f"/api/signer/tickets/{ticket}/signature",
                  {"signature": base64.b64encode(sig).decode()})
    print(f"Done: {result}")


if __name__ == "__main__":
    main()
