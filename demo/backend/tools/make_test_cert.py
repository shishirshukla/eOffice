"""Creates a self-signed RSA-2048 test certificate for trying the demo without a token.

Outputs, in demo/backend/test-certs/:
  <slug>.pfx  - import on Windows (double-click, "Current User", Personal store)
                to test the eOffice Signer without an HYP2003 token
  <slug>.pem  - private key + certificate, used by tools/sim_signer.py
  <slug>.cer  - certificate only; copy into trust-roots/ to mark it "trusted"

Usage:
  python tools/make_test_cert.py "Test Recommender" --password demo123
"""

import argparse
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

OUT_DIR = Path(__file__).resolve().parent.parent / "test-certs"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", help="Common name for the certificate, e.g. 'Test Recommender'")
    ap.add_argument("--password", default="demo123", help="Password for the .pfx file")
    args = ap.parse_args()

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "IN"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "eOffice Demo (TEST ONLY)"),
        x509.NameAttribute(NameOID.COMMON_NAME, args.name),
    ])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject).issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=True, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=False,
            crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
        .sign(key, hashes.SHA256())
    )

    OUT_DIR.mkdir(exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", args.name.lower()).strip("-")
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()) + cert.public_bytes(serialization.Encoding.PEM)
    (OUT_DIR / f"{slug}.pem").write_bytes(pem)
    (OUT_DIR / f"{slug}.cer").write_bytes(cert.public_bytes(serialization.Encoding.DER))
    pfx = pkcs12.serialize_key_and_certificates(
        args.name.encode(), key, cert, None,
        serialization.BestAvailableEncryption(args.password.encode()))
    (OUT_DIR / f"{slug}.pfx").write_bytes(pfx)
    print(f"Created {OUT_DIR / slug}.pfx / .pem / .cer  (pfx password: {args.password})")


if __name__ == "__main__":
    main()
