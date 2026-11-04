using System;
using System.Collections.Generic;
using System.Drawing;
using System.Security.Cryptography.X509Certificates;
using System.Windows.Forms;

namespace EOffice.Signer
{
    /// <summary>
    /// The single window of the signer: shows what is being signed (including
    /// the remarks that will be locked into the signature), lets the user pick
    /// a certificate, and performs the signing.
    /// </summary>
    internal sealed class SignForm : Form
    {
        private readonly SignRequest _request;
        private readonly ApiClient _api;
        private List<X509Certificate2> _certs = new List<X509Certificate2>();
        private bool _finished;

        private readonly Label _lblDocument = new Label();
        private readonly Label _lblStage = new Label();
        private readonly Label _lblSigner = new Label();
        private readonly TextBox _txtRemarks = new TextBox();
        private readonly ComboBox _cmbCert = new ComboBox();
        private readonly Button _btnRefresh = new Button();
        private readonly Button _btnSign = new Button();
        private readonly Button _btnCancel = new Button();
        private readonly Label _lblStatus = new Label();

        public SignForm(SignRequest request)
        {
            _request = request;
            _api = new ApiClient(request);
            BuildLayout();
            Load += async (s, e) => await LoadTicketAsync();
            FormClosing += OnClosing;
        }

        private void BuildLayout()
        {
            Text = AppInfo.Title + " " + AppInfo.Version;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            StartPosition = FormStartPosition.CenterScreen;
            TopMost = true;
            AutoScaleMode = AutoScaleMode.Dpi;
            ClientSize = new Size(620, 430);
            Font = new Font("Segoe UI", 9.5f);

            var layout = new TableLayoutPanel
            {
                Dock = DockStyle.Fill,
                Padding = new Padding(16),
                ColumnCount = 1,
                RowCount = 9,
            };
            Controls.Add(layout);

            var header = new Label
            {
                Text = "Sign with your DSC token",
                Font = new Font("Segoe UI", 13f, FontStyle.Bold),
                AutoSize = true,
                Margin = new Padding(0, 0, 0, 8),
            };
            layout.Controls.Add(header);

            foreach (var lbl in new[] { _lblDocument, _lblStage, _lblSigner })
            {
                lbl.AutoSize = true;
                lbl.MaximumSize = new Size(580, 0);
                lbl.Margin = new Padding(0, 2, 0, 2);
                layout.Controls.Add(lbl);
            }
            _lblDocument.Text = "Loading signing request...";

            layout.Controls.Add(new Label { Text = "Remarks (will be locked into your signature):", AutoSize = true, Margin = new Padding(0, 10, 0, 2) });
            _txtRemarks.Multiline = true;
            _txtRemarks.ReadOnly = true;
            _txtRemarks.ScrollBars = ScrollBars.Vertical;
            _txtRemarks.Size = new Size(580, 90);
            layout.Controls.Add(_txtRemarks);

            layout.Controls.Add(new Label { Text = "Certificate:", AutoSize = true, Margin = new Padding(0, 10, 0, 2) });
            var certRow = new FlowLayoutPanel { AutoSize = true, Margin = new Padding(0), WrapContents = false };
            _cmbCert.DropDownStyle = ComboBoxStyle.DropDownList;
            _cmbCert.Width = 490;
            _btnRefresh.Text = "Refresh";
            _btnRefresh.Width = 82;
            _btnRefresh.Click += (s, e) => LoadCertificates();
            certRow.Controls.Add(_cmbCert);
            certRow.Controls.Add(_btnRefresh);
            layout.Controls.Add(certRow);

            var buttons = new FlowLayoutPanel { AutoSize = true, FlowDirection = FlowDirection.LeftToRight, Margin = new Padding(0, 14, 0, 0) };
            _btnSign.Text = "Sign";
            _btnSign.Width = 120;
            _btnSign.Height = 32;
            _btnSign.Enabled = false;
            _btnSign.Click += async (s, e) => await SignAsync();
            _btnCancel.Text = "Cancel";
            _btnCancel.Width = 100;
            _btnCancel.Height = 32;
            _btnCancel.Click += (s, e) => Close();
            buttons.Controls.Add(_btnSign);
            buttons.Controls.Add(_btnCancel);
            layout.Controls.Add(buttons);

            _lblStatus.AutoSize = true;
            _lblStatus.MaximumSize = new Size(580, 0);
            _lblStatus.Margin = new Padding(0, 10, 0, 0);
            layout.Controls.Add(_lblStatus);

            AcceptButton = _btnSign;
            CancelButton = _btnCancel;
        }

        private async System.Threading.Tasks.Task LoadTicketAsync()
        {
            try
            {
                var t = await _api.GetTicketAsync();
                _lblDocument.Text = "Document:  " + ApiClient.Str(t, "documentTitle") +
                                    "  (" + ApiClient.Str(t, "reference") + ")";
                _lblStage.Text = "Stage:  " + ApiClient.Str(t, "slot") + ". " + ApiClient.Str(t, "role") +
                                 "  -  Action: " + ApiClient.Str(t, "action");
                _lblSigner.Text = "Signer:  " + ApiClient.Str(t, "name") + ", " + ApiClient.Str(t, "designation");
                string remarks = ApiClient.Str(t, "remarks");
                _txtRemarks.Text = string.IsNullOrEmpty(remarks) ? "(no remarks)" : remarks;
                LoadCertificates();
                Activate();
            }
            catch (UserFacingException ex)
            {
                Fail(ex.Message, notifyServer: false);
            }
        }

        private void LoadCertificates()
        {
            _cmbCert.Items.Clear();
            try
            {
                _certs = CertificatePicker.FindSigningCertificates();
            }
            catch (Exception ex)
            {
                _certs = new List<X509Certificate2>();
                SetStatus("Could not read certificates: " + ex.Message, true);
            }
            foreach (var c in _certs) _cmbCert.Items.Add(CertificatePicker.DisplayName(c));

            if (_certs.Count == 0)
            {
                _btnSign.Enabled = false;
                SetStatus("No signing certificate found. Insert your HYP2003 token, wait a few seconds and click Refresh.", true);
            }
            else
            {
                _cmbCert.SelectedIndex = 0;
                _btnSign.Enabled = true;
                SetStatus(_certs.Count == 1 ? "Ready. Click Sign and enter your token PIN."
                                            : "Choose your certificate, then click Sign.", false);
            }
        }

        private async System.Threading.Tasks.Task SignAsync()
        {
            if (_cmbCert.SelectedIndex < 0) return;
            var cert = _certs[_cmbCert.SelectedIndex];
            SetBusy(true);
            try
            {
                SetStatus("Preparing the document on the server...", false);
                byte[] digest = await _api.SubmitCertificateAsync(cert.RawData);

                SetStatus("Enter your token PIN in the PIN window...", false);
                // Runs on the UI thread so the driver's PIN window has this window as its owner.
                byte[] signature = CertificatePicker.SignDigest(cert, digest);

                SetStatus("Sending the signature...", false);
                var result = await _api.SubmitSignatureAsync(signature);

                _finished = true;
                Log.Write("Signed ticket " + _request.TicketShort + " with " + cert.Thumbprint +
                          ", new version " + ApiClient.Str(result, "version"));
                SetStatus("Signed successfully. You can return to the browser.", false);
                _btnCancel.Text = "Close";
                _btnCancel.Enabled = true;
                var timer = new Timer { Interval = 2500 };
                timer.Tick += (s, e) => { timer.Stop(); Close(); };
                timer.Start();
            }
            catch (UserFacingException ex)
            {
                Log.Write("Signing failed for " + _request.TicketShort + ": " + ex.Message);
                SetStatus(ex.Message, true);
                SetBusy(false);
            }
        }

        private void Fail(string message, bool notifyServer)
        {
            _finished = !notifyServer;
            SetStatus(message, true);
            _btnSign.Enabled = false;
            _btnRefresh.Enabled = false;
            _btnCancel.Text = "Close";
        }

        private void SetBusy(bool busy)
        {
            _btnSign.Enabled = !busy;
            _btnRefresh.Enabled = !busy;
            _cmbCert.Enabled = !busy;
            _btnCancel.Enabled = !busy;
            UseWaitCursor = busy;
        }

        private void SetStatus(string text, bool isError)
        {
            _lblStatus.Text = text;
            _lblStatus.ForeColor = isError ? Color.Firebrick : SystemColors.ControlText;
        }

        private async void OnClosing(object sender, FormClosingEventArgs e)
        {
            if (_finished) return;
            _finished = true;
            e.Cancel = true;          // tell the server first, then close
            await _api.CancelAsync("Closed in eOffice Signer");
            Close();
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing) _api.Dispose();
            base.Dispose(disposing);
        }
    }
}
