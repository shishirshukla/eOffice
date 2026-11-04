Put trusted root / CA certificates here (.cer or .der, DER-encoded).
The Verify button reports trusted=true only for signatures that chain to these.

- Testing: copy the test-certs/*.cer files created by tools/make_test_cert.py
- Real HYP2003 tokens: the Root Certifying Authority of India (CCA) certificate
  and the issuing CA certificates of your token provider
