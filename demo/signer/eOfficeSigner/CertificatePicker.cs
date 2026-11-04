using System;
using System.Collections.Generic;
using System.Linq;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;

namespace EOffice.Signer
{
    /// <summary>
    /// Finds signing certificates in the Windows "Personal" store.
    /// When an HYP2003 token is inserted, its driver places the token's
    /// certificate there, linked to the private key that stays on the token.
    /// </summary>
    internal static class CertificatePicker
    {
        public static List<X509Certificate2> FindSigningCertificates()
        {
            var result = new List<X509Certificate2>();
            var store = new X509Store(StoreName.My, StoreLocation.CurrentUser);
            store.Open(OpenFlags.ReadOnly | OpenFlags.OpenExistingOnly);
            try
            {
                DateTime now = DateTime.Now;
                foreach (X509Certificate2 cert in store.Certificates)
                {
                    if (!cert.HasPrivateKey) continue;
                    if (now < cert.NotBefore || now > cert.NotAfter) continue;
                    if (!AllowsSigning(cert)) continue;
                    using (RSA pub = cert.GetRSAPublicKey())
                    {
                        if (pub == null) continue;   // HYP2003 certificates are RSA
                    }
                    result.Add(cert);
                }
            }
            finally
            {
                store.Close();
            }
            return result.OrderBy(c => c.NotAfter).ToList();
        }

        public static string DisplayName(X509Certificate2 cert)
        {
            return cert.GetNameInfo(X509NameType.SimpleName, false) +
                   "  |  issued by " + cert.GetNameInfo(X509NameType.SimpleName, true) +
                   "  |  valid to " + cert.NotAfter.ToString("dd-MM-yyyy") +
                   "  |  " + cert.Thumbprint.Substring(0, 8);
        }

        /// <summary>Summary of available certificates, for the "installed" screen.</summary>
        public static string Describe()
        {
            try
            {
                var certs = FindSigningCertificates();
                if (certs.Count == 0)
                    return "(none found - insert your HYP2003 token)";
                var sb = new StringBuilder();
                foreach (var c in certs) sb.AppendLine("- " + DisplayName(c));
                return sb.ToString();
            }
            catch (CryptographicException ex)
            {
                return "(could not read the certificate store: " + ex.Message + ")";
            }
        }

        private static bool AllowsSigning(X509Certificate2 cert)
        {
            var ku = cert.Extensions.OfType<X509KeyUsageExtension>().FirstOrDefault();
            if (ku == null) return true;
            return (ku.KeyUsages & (X509KeyUsageFlags.DigitalSignature | X509KeyUsageFlags.NonRepudiation)) != 0;
        }

        /// <summary>
        /// Signs the server's SHA-256 digest with the token key (RSA PKCS#1 v1.5).
        /// The HYP2003 driver shows its own PIN window at this point.
        /// </summary>
        public static byte[] SignDigest(X509Certificate2 cert, byte[] digest)
        {
            using (RSA rsa = cert.GetRSAPrivateKey())
            {
                if (rsa == null)
                    throw new UserFacingException("The private key for this certificate is not available. Is the token inserted?");
                try
                {
                    return rsa.SignHash(digest, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
                }
                catch (CryptographicException ex)
                {
                    // Covers wrong PIN, PIN cancelled, token removed, token locked.
                    throw new UserFacingException("The token could not sign: " + ex.Message);
                }
            }
        }
    }
}
