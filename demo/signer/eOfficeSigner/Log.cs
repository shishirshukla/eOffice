using System;
using System.IO;

namespace EOffice.Signer
{
    /// <summary>
    /// Local log in %LOCALAPPDATA%\eOfficeSigner\logs. Never records the PIN
    /// or document content - only tickets (shortened), servers, thumbprints and results.
    /// </summary>
    internal static class Log
    {
        private static readonly object Gate = new object();

        public static void Write(string message)
        {
            try
            {
                string dir = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "eOfficeSigner", "logs");
                Directory.CreateDirectory(dir);
                string file = Path.Combine(dir, "signer-" + DateTime.Now.ToString("yyyyMMdd") + ".log");
                lock (Gate)
                {
                    File.AppendAllText(file, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "  " + message + Environment.NewLine);
                }
            }
            catch (Exception)
            {
                // Logging must never stop signing.
            }
        }
    }
}
