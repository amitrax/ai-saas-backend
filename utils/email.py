"""
Email Utility — Gmail SMTP
==========================
Sends transactional emails (OTP, password reset) via Gmail SMTP.
No extra packages — uses Python stdlib smtplib.

.env keys required:
    GMAIL_USER          = your Gmail address
    GMAIL_APP_PASSWORD  = 16-char App Password (https://myaccount.google.com/apppasswords)
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

GMAIL_USER = os.getenv("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
_IS_CONFIGURED = bool(GMAIL_USER and GMAIL_APP_PASSWORD and GMAIL_APP_PASSWORD != "your_16_char_app_password")


def _otp_html(otp: str) -> str:
    """Returns a styled HTML email body for OTP verification."""
    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0f0f1a;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0f0f1a;padding:40px 20px;">
    <tr>
      <td align="center">
        <table width="520" cellpadding="0" cellspacing="0"
               style="background:linear-gradient(135deg,#13131f 0%,#1a1a2e 100%);
                      border-radius:20px;border:1px solid #2a2a4a;overflow:hidden;">

          <!-- Header -->
          <tr>
            <td style="background:linear-gradient(135deg,#4f46e5,#7c3aed);
                       padding:36px 40px;text-align:center;">
              <div style="font-size:28px;font-weight:800;color:#fff;letter-spacing:-0.5px;">
                ⚡ NeuralForge
              </div>
              <div style="color:#c4b5fd;font-size:13px;margin-top:4px;letter-spacing:2px;
                          text-transform:uppercase;">
                AI Platform
              </div>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:44px 48px;">
              <h2 style="color:#fff;margin:0 0 12px;font-size:22px;font-weight:700;">
                Verify your email address
              </h2>
              <p style="color:#94a3b8;font-size:14px;line-height:1.7;margin:0 0 32px;">
                Enter the 6-digit code below to activate your NeuralForge account.
                This code expires in <strong style="color:#a78bfa;">10 minutes</strong>.
              </p>

              <!-- OTP Box -->
              <div style="background:#0f0f1a;border:2px solid #4f46e5;border-radius:16px;
                          padding:28px;text-align:center;margin-bottom:32px;">
                <div style="letter-spacing:20px;font-size:42px;font-weight:900;
                            color:#fff;font-family:'Courier New',monospace;padding-left:16px;">
                  {otp}
                </div>
              </div>

              <p style="color:#64748b;font-size:13px;line-height:1.6;margin:0;">
                If you didn't create a NeuralForge account, you can safely ignore this email.
                Never share this code with anyone.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:20px 48px 36px;border-top:1px solid #1e1e38;">
              <p style="color:#334155;font-size:12px;margin:0;text-align:center;">
                © 2025 NeuralForge AI · Built for the future
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def send_email(to_email: str, subject: str, html_content: str) -> bool:
    """
    Sends an HTML email via Gmail SMTP.

    Falls back to console print in dev mode when credentials are absent.

    Args:
        to_email     : Recipient email address.
        subject      : Email subject line.
        html_content : Full HTML body.

    Returns:
        True on success, False on failure.
    """
    load_dotenv(override=True)
    gmail_user = os.getenv("GMAIL_USER", "")
    gmail_app_password = os.getenv("GMAIL_APP_PASSWORD", "")
    is_configured = bool(gmail_user and gmail_app_password and gmail_app_password != "your_16_char_app_password")

    if not is_configured:
        print("[Email — DEV MODE] Gmail SMTP not configured. Printing email to console.")
        print(f"  To      : {to_email}")
        print(f"  Subject : {subject}")
        print(f"  Content : {html_content[:300]}...")
        return True

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"NeuralForge AI <{gmail_user}>"
        msg["To"] = to_email
        msg.attach(MIMEText(html_content, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_app_password)
            server.sendmail(gmail_user, to_email, msg.as_string())

        print(f"[Email] SUCCESS: Sent '{subject}' to {to_email}")
        return True

    except smtplib.SMTPAuthenticationError:
        print("[Email] ERROR: Auth failed — check GMAIL_USER & GMAIL_APP_PASSWORD in .env")
        return False
    except Exception as exc:
        print(f"[Email] ERROR: Exception: {exc}")
        return False


def send_otp_email(to_email: str, otp: str) -> bool:
    """Shortcut: sends a pre-styled OTP verification email."""
    return send_email(
        to_email=to_email,
        subject="Your NeuralForge Verification Code",
        html_content=_otp_html(otp),
    )
