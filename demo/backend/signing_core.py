"""Server-side half of split ("interrupted") PDF signing with pyHanko.

Flow:
  1. prepare_signature(): the server builds the signature (field, visible
     stamp with action + remarks, signed attributes) using the signer's
     certificate, and returns the SHA-256 digest the token must sign.
  2. The eOffice Signer on the user's PC signs that digest with the
     HYP2003 token (RSA PKCS#1 v1.5) and returns the raw signature.
  3. finish_signature(): the server checks the signature against the
     certificate and embeds it, producing the next PDF version.

The PDF itself never leaves the server; only a 32-byte digest does.
This module has no web-framework code so it can be reused in Django later.
"""

import asyncio
import base64
import hashlib
import textwrap
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO

from asn1crypto import cms, x509 as asn1_x509
from cryptography import x509 as crypto_x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.layout import AxisAlignment, Margins, SimpleBoxLayoutRule, InnerScaling
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.pdf_utils.text import TextBoxStyle
from pyhanko.sign import signers
from pyhanko.sign.fields import SigSeedSubFilter
from pyhanko.sign.signers.pdf_byterange import PreparedByteRangeDigest
from pyhanko.sign.signers.pdf_signer import PdfTBSDocument
from pyhanko.sign.validation import validate_pdf_signature
from pyhanko.stamp import TextStampStyle
from pyhanko_certvalidator import ValidationContext
from pyhanko_certvalidator.registry import SimpleCertificateStore

MD_ALGO = "sha256"
BYTES_RESERVED = 16384  # room for the CMS blob (cert chain + signature)
MAX_REMARKS = 500

STAMP_STYLE = TextStampStyle(
    border_width=1,
    stamp_text=(
        "%(action)s by %(name)s, %(designation)s\n"
        "Certificate: %(signer)s\n"
        "Signed on: %(ts)s\n"
        "Remarks:\n%(remarks)s"
    ),
    timestamp_format="%d-%m-%Y %H:%M:%S %Z",
    text_box_style=TextBoxStyle(font_size=9),
    inner_content_layout=SimpleBoxLayoutRule(
        x_align=AxisAlignment.ALIGN_MIN, y_align=AxisAlignment.ALIGN_MAX,
        margins=Margins.uniform(6), inner_content_scaling=InnerScaling.SHRINK_TO_FIT),
)


class SigningError(Exception):
    """Raised for any problem the user or signer app should be told about."""


@dataclass
class PreparedSignature:
    prepared_pdf: bytes          # PDF with an empty, reserved signature slot
    state: dict                  # JSON-serialisable data needed to finish
    digest_to_sign: bytes        # SHA-256 of the DER-encoded signed attributes


def _wrap_remarks(remarks: str) -> str:
    remarks = (remarks or "").strip() or "(no remarks)"
    lines = []
    for para in remarks.splitlines():
        lines.extend(textwrap.wrap(para, width=95) or [""])
    return "\n".join(lines)


def load_certificate(cert_der: bytes) -> asn1_x509.Certificate:
    """Parses the signer's certificate and applies basic demo checks."""
    try:
        cert = asn1_x509.Certificate.load(cert_der)
        ccert = crypto_x509.load_der_x509_certificate(cert_der)
    except Exception as exc:  # noqa: BLE001 - any parse failure is a bad request
        raise SigningError(f"Certificate could not be read: {exc}") from exc

    now = datetime.now(timezone.utc)
    if not (ccert.not_valid_before_utc <= now <= ccert.not_valid_after_utc):
        raise SigningError("Certificate is expired or not yet valid.")
    if not isinstance(ccert.public_key(), rsa.RSAPublicKey):
        raise SigningError("Only RSA certificates are supported (HYP2003 tokens use RSA).")
    try:
        ku = ccert.extensions.get_extension_for_class(crypto_x509.KeyUsage).value
        if not (ku.digital_signature or ku.content_commitment):
            raise SigningError("Certificate is not allowed for digital signatures.")
    except crypto_x509.ExtensionNotFound:
        pass
    return cert


def cert_thumbprint(cert_der: bytes) -> str:
    """SHA-1 thumbprint in the same format Windows shows (upper-case hex)."""
    return hashlib.sha1(cert_der).hexdigest().upper()


def cert_subject_cn(cert_der: bytes) -> str:
    ccert = crypto_x509.load_der_x509_certificate(cert_der)
    attrs = ccert.subject.get_attributes_for_oid(crypto_x509.NameOID.COMMON_NAME)
    return attrs[0].value if attrs else ccert.subject.rfc4514_string()


async def _prepare(pdf_bytes, field_name, cert, stamp_params, reason, location):
    registry = SimpleCertificateStore.from_certs([cert])
    # Placeholder signature value: only used to estimate sizes at this stage.
    ext_signer = signers.ExternalSigner(
        signing_cert=cert, cert_registry=registry, signature_value=bytes(512))
    meta = signers.PdfSignatureMetadata(
        field_name=field_name, md_algorithm=MD_ALGO,
        subfilter=SigSeedSubFilter.PADES, reason=reason, location=location)
    pdf_signer = signers.PdfSigner(meta, signer=ext_signer, stamp_style=STAMP_STYLE)

    writer = IncrementalPdfFileWriter(BytesIO(pdf_bytes))
    prep_digest, tbs_document, output = await pdf_signer.async_digest_doc_for_signing(
        writer, existing_fields_only=True, bytes_reserved=BYTES_RESERVED,
        appearance_text_params=stamp_params)
    if tbs_document.post_sign_instructions is not None:
        # Only produced for timestamps / LTV, which this demo does not use.
        raise SigningError("Unexpected post-sign instructions.")

    signed_attrs = await ext_signer.signed_attrs(
        prep_digest.document_digest, MD_ALGO, use_pades=True)
    signed_attrs_der = signed_attrs.dump()
    output.seek(0)
    return output.read(), prep_digest, signed_attrs_der


def prepare_signature(pdf_bytes: bytes, field_name: str, cert_der: bytes, *,
                      name: str, designation: str, action: str, remarks: str,
                      location: str = "eOffice demo") -> PreparedSignature:
    cert = load_certificate(cert_der)
    if len(remarks or "") > MAX_REMARKS:
        raise SigningError(f"Remarks must be at most {MAX_REMARKS} characters.")
    stamp_params = {
        "action": action, "name": name, "designation": designation,
        "remarks": _wrap_remarks(remarks),
    }
    prepared_pdf, prep_digest, signed_attrs_der = asyncio.run(
        _prepare(pdf_bytes, field_name, cert, stamp_params, reason=action, location=location))

    state = {
        "cert_der": base64.b64encode(cert_der).decode(),
        "signed_attrs_der": base64.b64encode(signed_attrs_der).decode(),
        "document_digest": base64.b64encode(prep_digest.document_digest).decode(),
        "reserved_region_start": prep_digest.reserved_region_start,
        "reserved_region_end": prep_digest.reserved_region_end,
    }
    return PreparedSignature(prepared_pdf, state, hashlib.sha256(signed_attrs_der).digest())


async def _finish(prepared_pdf, state, signature):
    cert = asn1_x509.Certificate.load(base64.b64decode(state["cert_der"]))
    registry = SimpleCertificateStore.from_certs([cert])
    ext_signer = signers.ExternalSigner(
        signing_cert=cert, cert_registry=registry, signature_value=signature)
    signed_attrs = cms.CMSAttributes.load(base64.b64decode(state["signed_attrs_der"]))
    sig_cms = await ext_signer.async_sign_prescribed_attributes(
        MD_ALGO, signed_attrs=signed_attrs)
    prep_digest = PreparedByteRangeDigest(
        document_digest=base64.b64decode(state["document_digest"]),
        reserved_region_start=state["reserved_region_start"],
        reserved_region_end=state["reserved_region_end"])
    out = BytesIO(prepared_pdf)
    await PdfTBSDocument.async_finish_signing(out, prepared_digest=prep_digest, signature_cms=sig_cms)
    return out.getvalue()


def finish_signature(prepared_pdf: bytes, state: dict, signature: bytes) -> bytes:
    """Verifies the token's signature and embeds it. Returns the signed PDF."""
    cert_der = base64.b64decode(state["cert_der"])
    signed_attrs_der = base64.b64decode(state["signed_attrs_der"])
    public_key = crypto_x509.load_der_x509_certificate(cert_der).public_key()
    try:
        public_key.verify(signature, signed_attrs_der, padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature as exc:
        raise SigningError(
            "The signature does not match the certificate. "
            "Was the right certificate / token used?") from exc
    return asyncio.run(_finish(prepared_pdf, state, signature))


def verify_pdf(pdf_bytes: bytes, trust_roots_der: list[bytes]) -> list[dict]:
    """Lists every signature in the PDF with its integrity and trust status."""
    roots = [asn1_x509.Certificate.load(d) for d in trust_roots_der]
    vc = ValidationContext(trust_roots=roots, allow_fetching=False)
    reader = PdfFileReader(BytesIO(pdf_bytes))
    results = []
    for sig in reader.embedded_signatures:
        status = validate_pdf_signature(sig, vc)
        results.append({
            "field": sig.field_name,
            "signer": status.signing_cert.subject.human_friendly,
            "signed_at": str(status.signer_reported_dt) if status.signer_reported_dt else None,
            "intact": status.intact,
            "valid": status.valid,
            "trusted": status.trusted,
            "coverage": status.coverage.name if status.coverage else None,
            "modification_level": status.modification_level.name if status.modification_level else None,
        })
    return results
