using System;
using System.Configuration;
using System.Linq;
using System.Text.RegularExpressions;
using System.Web;
using System.Windows.Forms;

namespace EOffice.Signer
{
    /// <summary>
    /// Entry point. Windows starts the app with the link the browser opened, e.g.
    ///   eOfficeSigner.exe "eoffice-sign://sign?ticket=XYZ&amp;server=http%3A%2F%2F127.0.0.1%3A8000"
    /// </summary>
    internal static class Program
    {
        internal const string Scheme = "eoffice-sign";
        private static readonly Regex TicketPattern = new Regex("^[A-Za-z0-9_-]{16,128}$");

        [STAThread]
        private static int Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            try
            {
                if (args.Length == 0)
                {
                    MessageBox.Show(
                        "eOffice Signer " + AppInfo.Version + " is installed.\n\n" +
                        "Start signing from eOffice in your browser; this app opens automatically.\n\n" +
                        "Certificates available for signing:\n" + CertificatePicker.Describe(),
                        AppInfo.Title, MessageBoxButtons.OK, MessageBoxIcon.Information);
                    return 0;
                }

                SignRequest request = ParseLink(args[0]);
                Log.Write("Started for ticket " + request.TicketShort + " on " + request.Server);
                Application.Run(new SignForm(request));
                return 0;
            }
            catch (UserFacingException ex)
            {
                Log.Write("Refused: " + ex.Message);
                MessageBox.Show(ex.Message, AppInfo.Title, MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return 1;
            }
            catch (Exception ex)
            {
                Log.Write("Unexpected error: " + ex);
                MessageBox.Show("Unexpected error: " + ex.Message, AppInfo.Title,
                    MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 2;
            }
        }

        private static SignRequest ParseLink(string link)
        {
            Uri uri;
            if (!Uri.TryCreate(link, UriKind.Absolute, out uri) ||
                !string.Equals(uri.Scheme, Scheme, StringComparison.OrdinalIgnoreCase) ||
                !string.Equals(uri.Host, "sign", StringComparison.OrdinalIgnoreCase))
            {
                throw new UserFacingException("This is not a valid eOffice signing link.");
            }

            var query = HttpUtility.ParseQueryString(uri.Query);
            string ticket = query["ticket"] ?? "";
            string server = (query["server"] ?? "").TrimEnd('/');

            if (!TicketPattern.IsMatch(ticket))
                throw new UserFacingException("The signing link has an invalid ticket.");

            Uri serverUri;
            if (!Uri.TryCreate(server, UriKind.Absolute, out serverUri) ||
                (serverUri.Scheme != Uri.UriSchemeHttps && serverUri.Scheme != Uri.UriSchemeHttp))
                throw new UserFacingException("The signing link has an invalid server address.");

            string origin = serverUri.GetLeftPart(UriPartial.Authority).TrimEnd('/');
            string[] allowed = (ConfigurationManager.AppSettings["AllowedServers"] ?? "")
                .Split(new[] { ';' }, StringSplitOptions.RemoveEmptyEntries)
                .Select(s => s.Trim().TrimEnd('/'))
                .ToArray();
            if (!allowed.Any(a => string.Equals(a, origin, StringComparison.OrdinalIgnoreCase)))
            {
                throw new UserFacingException(
                    "This signing request comes from a server that is not approved:\n" + origin +
                    "\n\nAsk IT to add it to AllowedServers in eOfficeSigner.exe.config.");
            }

            return new SignRequest(ticket, origin);
        }
    }

    internal sealed class SignRequest
    {
        public SignRequest(string ticket, string server)
        {
            Ticket = ticket;
            Server = server;
        }

        public string Ticket { get; private set; }
        public string Server { get; private set; }
        public string TicketShort { get { return Ticket.Substring(0, 8) + "..."; } }
    }

    /// <summary>An error whose message is safe and useful to show the user.</summary>
    internal sealed class UserFacingException : Exception
    {
        public UserFacingException(string message) : base(message) { }
    }

    internal static class AppInfo
    {
        public const string Title = "eOffice Signer";

        public static string Version
        {
            get
            {
                var v = typeof(AppInfo).Assembly.GetName().Version;
                return v.Major + "." + v.Minor + "." + v.Build;
            }
        }
    }
}
