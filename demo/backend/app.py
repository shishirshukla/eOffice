"""eOffice signing demo backend (Flask).

One demo proposal, three signature slots (Recommender -> Sanctioning
authority -> Control). Each signer enters remarks in the browser, clicks
Sign, and the eOffice Signer app on their Windows PC signs with the
HYP2003 token.

Run:   python app.py               (listens on http://127.0.0.1:8000)
       python app.py --host 0.0.0.0 --public-url http://<this-pc-ip>:8000
"""

import argparse
import base64
import json
import re
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from flask import Flask, abort, jsonify, render_template, request, send_file

import pdf_template
import signing_core as sc

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
VERSIONS = DATA / "versions"
TICKETS = DATA / "tickets"
TRUST_ROOTS = BASE / "trust-roots"
STATE_FILE = DATA / "document.json"

TICKET_TTL_SECONDS = 5 * 60
MIN_SIGNER_VERSION = (0, 1, 0)
TICKET_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")

app = Flask(__name__)
app.config["PUBLIC_URL"] = "http://127.0.0.1:8000"
_lock = threading.Lock()  # one signature at a time on the document (FR-49)


# ---------------------------------------------------------------- storage

def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _log(state: dict, event: str, **details) -> None:
    state["audit"].append({"at": _now(), "event": event, **details})


def load_state() -> dict:
    if not STATE_FILE.exists():
        return reset_document()
    return json.loads(STATE_FILE.read_text())


def save_state(state: dict) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(STATE_FILE)


def reset_document() -> dict:
    DATA.mkdir(exist_ok=True)
    for d in (VERSIONS, TICKETS):
        d.mkdir(exist_ok=True)
        for f in d.iterdir():
            f.unlink()
    ref = f"DEMO/{datetime.now():%Y%m%d-%H%M%S}"
    (VERSIONS / "v0.pdf").write_bytes(pdf_template.build_version0(ref))
    state = {
        "reference": ref,
        "title": pdf_template.DOC_TITLE,
        "current_version": 0,
        "slots": [{"no": s["no"], "role": s["role"], "field": s["field"],
                   "default_action": s["default_action"], "status": "pending"}
                  for s in pdf_template.SLOTS],
        "registered_certs": {},   # signer name (lower-case) -> thumbprint (FR-46, first use)
        "audit": [],
    }
    _log(state, "document_created", reference=ref)
    save_state(state)
    return state


def version_path(n: int) -> Path:
    return VERSIONS / f"v{n}.pdf"


def load_ticket(ticket_id: str) -> dict:
    if not TICKET_RE.match(ticket_id or ""):
        abort(404)
    p = TICKETS / f"{ticket_id}.json"
    if not p.exists():
        abort(404)
    return json.loads(p.read_text())


def save_ticket(t: dict) -> None:
    (TICKETS / f"{t['id']}.json").write_text(json.dumps(t, indent=2))


def next_slot(state: dict):
    return next((s for s in state["slots"] if s["status"] != "signed"), None)


def trust_roots() -> list[bytes]:
    if not TRUST_ROOTS.exists():
        return []
    return [p.read_bytes() for p in TRUST_ROOTS.iterdir() if p.suffix.lower() in (".cer", ".der")]


def api_error(message: str, status: int = 400):
    return jsonify({"error": message}), status


def check_ticket_usable(t: dict, expected_status: str):
    if time.time() > t["expires_at"]:
        t["status"] = "expired"
        save_ticket(t)
        return api_error("This signing request has expired. Click Sign again in eOffice.", 410)
    if t["status"] != expected_status:
        return api_error(f"This signing request is already {t['status']}.", 409)
    return None


def check_signer_version():
    raw = request.headers.get("X-eOffice-Signer-Version", "0.0.0")
    try:
        ver = tuple(int(x) for x in raw.split(".")[:3])
    except ValueError:
        ver = (0, 0, 0)
    if ver < MIN_SIGNER_VERSION:
        return api_error("Please update the eOffice Signer to version "
                         + ".".join(map(str, MIN_SIGNER_VERSION)) + " or later.", 426)
    return None


# ---------------------------------------------------------------- browser pages

@app.get("/")
def index():
    state = load_state()
    return render_template("index.html", state=state, nxt=next_slot(state),
                           max_remarks=sc.MAX_REMARKS)


@app.post("/reset")
def reset():
    with _lock:
        reset_document()
    return jsonify({"ok": True})


@app.get("/versions/<int:n>.pdf")
def download_version(n: int):
    p = version_path(n)
    if not p.exists():
        abort(404)
    inline = request.args.get("inline") == "1"
    return send_file(p, mimetype="application/pdf", as_attachment=not inline,
                     download_name=f"eoffice-demo-v{n}.pdf")


@app.get("/verify")
def verify():
    state = load_state()
    pdf = version_path(state["current_version"]).read_bytes()
    return jsonify({"version": state["current_version"],
                    "signatures": sc.verify_pdf(pdf, trust_roots())})


@app.post("/slots/<int:no>/start")
def start_signing(no: int):
    """Browser: the signer has entered remarks and clicked Sign."""
    body = request.get_json(force=True)
    name = (body.get("name") or "").strip()
    designation = (body.get("designation") or "").strip()
    action = (body.get("action") or "").strip()
    remarks = (body.get("remarks") or "").strip()
    if not name or not designation or not action:
        return api_error("Name, designation and action are required.")
    if len(remarks) > sc.MAX_REMARKS:
        return api_error(f"Remarks must be at most {sc.MAX_REMARKS} characters.")

    state = load_state()
    slot = next_slot(state)
    if slot is None:
        return api_error("All three signatures are already done.")
    if slot["no"] != no:
        return api_error(f"Slot {slot['no']} must be signed first.")

    ticket = {
        "id": secrets.token_urlsafe(24),
        "slot": no, "field": slot["field"], "role": slot["role"],
        "name": name, "designation": designation, "action": action, "remarks": remarks,
        "base_version": state["current_version"],
        "status": "waiting_for_signer", "message": "",
        "created_at": time.time(), "expires_at": time.time() + TICKET_TTL_SECONDS,
    }
    save_ticket(ticket)
    _log(state, "signing_started", slot=no, name=name, ticket=ticket["id"][:8])
    save_state(state)

    launch = (f"eoffice-sign://sign?ticket={ticket['id']}"
              f"&server={quote(app.config['PUBLIC_URL'], safe='')}")
    return jsonify({"ticket": ticket["id"], "launch_url": launch,
                    "expires_in": TICKET_TTL_SECONDS})


@app.get("/tickets/<ticket_id>/status")
def ticket_status(ticket_id: str):
    """Browser polls this while the eOffice Signer is working."""
    t = load_ticket(ticket_id)
    if t["status"] not in ("signed", "failed", "cancelled") and time.time() > t["expires_at"]:
        t["status"] = "expired"
        save_ticket(t)
    return jsonify({"status": t["status"], "message": t.get("message", "")})


# ---------------------------------------------------------------- signer app API

@app.get("/api/signer/tickets/<ticket_id>")
def api_get_ticket(ticket_id: str):
    if (err := check_signer_version()):
        return err
    t = load_ticket(ticket_id)
    if (err := check_ticket_usable(t, "waiting_for_signer")):
        return err
    state = load_state()
    return jsonify({
        "documentTitle": state["title"], "reference": state["reference"],
        "slot": t["slot"], "role": t["role"], "name": t["name"],
        "designation": t["designation"], "action": t["action"], "remarks": t["remarks"],
        "expiresInSeconds": int(t["expires_at"] - time.time()),
    })


@app.post("/api/signer/tickets/<ticket_id>/certificate")
def api_submit_certificate(ticket_id: str):
    """Step 1: signer app sends the chosen certificate; server returns the digest."""
    if (err := check_signer_version()):
        return err
    t = load_ticket(ticket_id)
    if (err := check_ticket_usable(t, "waiting_for_signer")):
        return err
    try:
        cert_der = base64.b64decode(request.get_json(force=True)["certificate"])
    except Exception:  # noqa: BLE001
        return api_error("Certificate missing or not base64.")

    with _lock:
        state = load_state()
        if state["current_version"] != t["base_version"]:
            return api_error("The document changed since this request was created.", 409)
        thumb = sc.cert_thumbprint(cert_der)
        registered = state["registered_certs"].get(t["name"].lower())
        if registered and registered != thumb:
            return api_error(f"{t['name']} is registered with a different certificate "
                             f"({registered[:12]}...). Use that certificate.", 403)
        try:
            prepared = sc.prepare_signature(
                version_path(t["base_version"]).read_bytes(), t["field"], cert_der,
                name=t["name"], designation=t["designation"],
                action=t["action"], remarks=t["remarks"])
        except sc.SigningError as exc:
            return api_error(str(exc))

        (TICKETS / f"{t['id']}.prepared.pdf").write_bytes(prepared.prepared_pdf)
        t["signing_state"] = prepared.state
        t["cert_thumbprint"] = thumb
        t["cert_subject"] = sc.cert_subject_cn(cert_der)
        t["status"] = "waiting_for_token"
        save_ticket(t)

    return jsonify({"digest": base64.b64encode(prepared.digest_to_sign).decode(),
                    "digestAlgorithm": "SHA256", "padding": "PKCS1"})


@app.post("/api/signer/tickets/<ticket_id>/signature")
def api_submit_signature(ticket_id: str):
    """Step 2: signer app sends the token's signature; server embeds it."""
    if (err := check_signer_version()):
        return err
    t = load_ticket(ticket_id)
    if (err := check_ticket_usable(t, "waiting_for_token")):
        return err
    try:
        signature = base64.b64decode(request.get_json(force=True)["signature"])
    except Exception:  # noqa: BLE001
        return api_error("Signature missing or not base64.")

    with _lock:
        state = load_state()
        if state["current_version"] != t["base_version"]:
            return api_error("The document changed since this request was created.", 409)
        prepared_path = TICKETS / f"{t['id']}.prepared.pdf"
        try:
            signed_pdf = sc.finish_signature(prepared_path.read_bytes(), t["signing_state"], signature)
        except sc.SigningError as exc:
            t["status"], t["message"] = "failed", str(exc)
            save_ticket(t)
            _log(state, "signing_failed", slot=t["slot"], reason=str(exc))
            save_state(state)
            return api_error(str(exc))

        new_version = state["current_version"] + 1
        version_path(new_version).write_bytes(signed_pdf)
        prepared_path.unlink(missing_ok=True)
        state["current_version"] = new_version
        state["registered_certs"].setdefault(t["name"].lower(), t["cert_thumbprint"])
        for s in state["slots"]:
            if s["no"] == t["slot"]:
                s.update(status="signed", name=t["name"], designation=t["designation"],
                         action=t["action"], remarks=t["remarks"], signed_at=_now(),
                         cert_subject=t["cert_subject"], cert_thumbprint=t["cert_thumbprint"],
                         version=new_version)
        _log(state, "signed", slot=t["slot"], name=t["name"], version=new_version,
             cert=t["cert_thumbprint"])
        if next_slot(state) is None:
            _log(state, "completed", final_version=new_version)
        save_state(state)
        t["status"] = "signed"
        t.pop("signing_state", None)
        save_ticket(t)

    return jsonify({"status": "signed", "version": new_version})


@app.post("/api/signer/tickets/<ticket_id>/cancel")
def api_cancel(ticket_id: str):
    t = load_ticket(ticket_id)
    if t["status"] in ("waiting_for_signer", "waiting_for_token"):
        reason = (request.get_json(silent=True) or {}).get("reason", "Cancelled in signer")
        t["status"], t["message"] = "cancelled", str(reason)[:200]
        save_ticket(t)
    return jsonify({"status": t["status"]})


# ---------------------------------------------------------------- main

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--public-url", help="URL the signer app uses to reach this server")
    args = ap.parse_args()
    app.config["PUBLIC_URL"] = (args.public_url or f"http://{args.host}:{args.port}").rstrip("/")
    if args.host == "0.0.0.0" and not args.public_url:
        ap.error("--public-url is required with --host 0.0.0.0")
    load_state()
    print(f"eOffice demo on {app.config['PUBLIC_URL']}")
    app.run(host=args.host, port=args.port, threaded=True)
