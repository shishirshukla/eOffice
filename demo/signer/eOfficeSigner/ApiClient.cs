using System;
using System.Collections.Generic;
using System.Configuration;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using System.Web.Script.Serialization;

namespace EOffice.Signer
{
    /// <summary>Talks to the eOffice server's signer API.</summary>
    internal sealed class ApiClient : IDisposable
    {
        private readonly HttpClient _http;
        private readonly string _ticket;
        private readonly JavaScriptSerializer _json = new JavaScriptSerializer();

        public ApiClient(SignRequest request)
        {
            // Use the OS TLS settings (TLS 1.2 / 1.3 on Windows 11).
            ServicePointManager.SecurityProtocol = SecurityProtocolType.SystemDefault;

            int timeout;
            if (!int.TryParse(ConfigurationManager.AppSettings["RequestTimeoutSeconds"], out timeout))
                timeout = 30;

            _http = new HttpClient
            {
                BaseAddress = new Uri(request.Server + "/"),
                Timeout = TimeSpan.FromSeconds(timeout),
            };
            _http.DefaultRequestHeaders.Add("X-eOffice-Signer-Version", AppInfo.Version);
            _ticket = request.Ticket;
        }

        public Task<Dictionary<string, object>> GetTicketAsync()
        {
            return SendAsync(HttpMethod.Get, "api/signer/tickets/" + _ticket, null);
        }

        /// <summary>Sends the chosen certificate; returns the 32-byte SHA-256 digest to sign.</summary>
        public async Task<byte[]> SubmitCertificateAsync(byte[] certificateDer)
        {
            var result = await SendAsync(HttpMethod.Post, "api/signer/tickets/" + _ticket + "/certificate",
                new Dictionary<string, object> { { "certificate", Convert.ToBase64String(certificateDer) } });

            if (Str(result, "digestAlgorithm") != "SHA256" || Str(result, "padding") != "PKCS1")
                throw new UserFacingException("The server asked for an unsupported signature type.");

            byte[] digest = Convert.FromBase64String(Str(result, "digest"));
            if (digest.Length != 32)
                throw new UserFacingException("The server sent an invalid digest.");
            return digest;
        }

        public Task<Dictionary<string, object>> SubmitSignatureAsync(byte[] signature)
        {
            return SendAsync(HttpMethod.Post, "api/signer/tickets/" + _ticket + "/signature",
                new Dictionary<string, object> { { "signature", Convert.ToBase64String(signature) } });
        }

        public async Task CancelAsync(string reason)
        {
            try
            {
                await SendAsync(HttpMethod.Post, "api/signer/tickets/" + _ticket + "/cancel",
                    new Dictionary<string, object> { { "reason", reason } });
            }
            catch (Exception ex)
            {
                Log.Write("Cancel notification failed: " + ex.Message);
            }
        }

        public static string Str(Dictionary<string, object> d, string key)
        {
            object v;
            return d != null && d.TryGetValue(key, out v) && v != null ? Convert.ToString(v) : "";
        }

        private async Task<Dictionary<string, object>> SendAsync(HttpMethod method, string path,
            Dictionary<string, object> body)
        {
            var msg = new HttpRequestMessage(method, path);
            if (body != null)
                msg.Content = new StringContent(_json.Serialize(body), Encoding.UTF8, "application/json");

            HttpResponseMessage response;
            try
            {
                response = await _http.SendAsync(msg);
            }
            catch (HttpRequestException ex)
            {
                throw new UserFacingException("Could not reach the eOffice server: " + ex.Message);
            }
            catch (TaskCanceledException)
            {
                throw new UserFacingException("The eOffice server did not respond in time.");
            }

            string text = await response.Content.ReadAsStringAsync();
            Dictionary<string, object> data = null;
            try
            {
                data = _json.Deserialize<Dictionary<string, object>>(text);
            }
            catch (ArgumentException)
            {
                // Not JSON; handled below.
            }

            if (!response.IsSuccessStatusCode)
            {
                string error = Str(data, "error");
                throw new UserFacingException(string.IsNullOrEmpty(error)
                    ? "The eOffice server returned an error (" + (int)response.StatusCode + ")."
                    : error);
            }
            if (data == null)
                throw new UserFacingException("The eOffice server sent an unexpected response.");
            return data;
        }

        public void Dispose()
        {
            _http.Dispose();
        }
    }
}
