# eOffice signing demo

A proof of concept for the signing design in [FRS section 15.3](../docs/eOffice-FRS.md). It lets three people sign one demo PDF in turn (Recommender, then Sanctioning authority, then Control), each with remarks. The signatures are made on HYP2003 tokens through the in-house **eOffice Signer**.

```
demo/
  backend/            Python (Flask + pyHanko) demo server
    app.py            web page + signer API
    signing_core.py   split signing logic (reusable later in Django)
    pdf_template.py   demo proposal PDF with 3 empty signature fields
    tools/            test certificate maker + simulated signer
  signer/             eOffice Signer (.NET Framework 4.8.1, C#)
    eOfficeSigner/    the app
    installer/        WiX v5 per-user MSI
    build.ps1         builds exe + MSI (Windows)
    install-dev.ps1   quick install without MSI (Windows)
```

## How a signature happens

1. In the browser, the signer enters name, designation, action and remarks, then clicks **Sign with DSC token**.
2. The server creates a one-time ticket, valid for 5 minutes, and the browser opens `eoffice-sign://sign?ticket=…&server=…`.
3. Windows starts the **eOffice Signer**. It shows the document, the stage and the remarks, and lists the certificates found in the Windows store.
4. The Signer sends the chosen certificate. The server builds the signature, with a visible stamp holding the action, name, certificate, time and remarks, and returns a 32-byte SHA-256 digest.
5. The Signer signs the digest with the token. **The HYP2003 driver asks for the PIN.** The Signer then posts the signature back.
6. The server checks that the signature matches the certificate and embeds it as a new PDF version (v1, v2, v3). The browser refreshes.

The PDF never leaves the server, and the PIN never leaves the token driver.

## 1. Run the backend

You need Python 3.11 or later, on any OS.

```bash
cd demo/backend
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py                         # http://127.0.0.1:8000
```

To run the server on one machine and sign from another Windows PC:

```bash
python app.py --host 0.0.0.0 --public-url http://<server-ip>:8000
```

Then add that URL to the Signer's allowed servers. See step 2, `-Server`.

## 2. Build and install the eOffice Signer (Windows)

On the **build machine**, install the .NET SDK 8 or later. User PCs need only the built-in .NET Framework 4.8.1.

```powershell
cd demo\signer
powershell -ExecutionPolicy Bypass -File .\build.ps1
msiexec /i installer\bin\Release\eOfficeSigner-0.1.0.msi
```

The MSI installs **per user** and needs no admin rights:
- Files go to `%LOCALAPPDATA%\Programs\eOfficeSigner`.
- It registers `eoffice-sign://` under `HKCU\Software\Classes`.
- For a silent install, use `msiexec /i … /qn`.

**Quick test without the MSI:**

```powershell
dotnet build .\eOfficeSigner\eOfficeSigner.csproj -c Release
powershell -ExecutionPolicy Bypass -File .\install-dev.ps1 -Server http://<server-ip>:8000
```

**Allowed servers:** the Signer refuses links from servers not listed in `AllowedServers` in `eOfficeSigner.exe.config`. The default list is `127.0.0.1:8000` and `localhost:8000`.

Run `eOfficeSigner.exe` with no arguments to see its version and the certificates it can find. Logs are in `%LOCALAPPDATA%\eOfficeSigner\logs`.

## 3. Test

### With the HYP2003 token (the real test)

1. Insert the token. Check that its certificate appears in `certmgr.msc` under **Personal > Certificates**.
2. Open the demo page and fill slot 1. Click **Sign with DSC token**, allow the browser to open eOffice Signer, click **Sign**, and enter the PIN.
3. Repeat for slots 2 and 3, ideally with different people's tokens.
4. Download v3 and open it in **Adobe Reader**. All three signatures should show, with earlier signatures still valid. Trust shows as "unknown" until the CCA root and the CA chain are trusted in Reader.
5. Click **Verify signatures in latest version**. Every signature should show `intact=true valid=true`.

### Without a token (Windows)

```bash
python tools/make_test_cert.py "Test Recommender" --password demo123
```

Double-click `test-certs\test-recommender.pfx` and import it to **Current User > Personal**. The Signer will list it like a token certificate. No PIN is asked, because the key is not on a token.

### Without Windows (backend only)

`tools/sim_signer.py` makes the same API calls as the Signer, using a `.pem` test certificate. Copy the `launch_url` from the browser's network tab, or from the `/slots/<n>/start` response, then run:

```bash
python tools/sim_signer.py "<eoffice-sign:// link>" test-certs/test-recommender.pem
```

### Trust

Copy `.cer` files into `backend/trust-roots/` to have Verify report `trusted=true`. Use the test certificates for test signatures, or the Indian CCA root and CA certificates for real tokens.

## Demo rules that carry into the real application

| Rule | FRS |
| --- | --- |
| Slots must be signed in order; a 4th signature is refused | FR-06 |
| A person's certificate is registered on first use, and a different certificate is refused afterwards | FR-46 |
| Expired, non-RSA or non-signing certificates are refused | FR-46 |
| A signature that does not match the certificate is refused | FR-45 |
| One signature at a time; a request fails if the document changed meanwhile | FR-49 |
| Remarks are printed in the signature box and locked by the signature (max 500 characters) | FR-39 |
| Signer versions below the server's minimum are asked to update | FRS 15.3 |
| Tickets are single-use and expire after 5 minutes | FRS 15.3 |

**Not in the demo:** login, the database (the demo uses JSON files under `backend/data/`), email, timestamping and CRL/OCSP checks. Production must use HTTPS only.
