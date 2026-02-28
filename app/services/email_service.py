"""
AirRev Engine — Email Delivery Service
Sends property reports and CREB summaries via email.

Supports:
  - Resend (recommended — simple, reliable, great for transactional email)
  - SendGrid (alternative)
  - SMTP fallback

Set EMAIL_PROVIDER and credentials in .env.
Sign up at resend.com — free tier is 3,000 emails/mo.
"""

import httpx
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional
from datetime import datetime
from app.core.config import settings

logger = logging.getLogger(__name__)


# ── Email HTML templates ───────────────────────────────────────

def _property_report_email_html(address: str, summary: dict, mls_number: str) -> str:
    rec = summary.get("recommendation", "")
    strategy = summary.get("best_strategy", "")
    insight = summary.get("key_insight", "")
    rec_color = {
        "Strong Buy": "#10B981", "Buy": "#0EA5E9",
        "Hold": "#F59E0B", "Avoid": "#EF4444",
    }.get(rec, "#2563EB")

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#F8FAFC;">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center" style="padding:32px 16px;">
      <table width="600" cellpadding="0" cellspacing="0" style="background:white;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">

        <!-- Header -->
        <tr><td style="background:#0F172A;padding:28px 32px;">
          <p style="margin:0;color:#2563EB;font-size:12px;font-weight:700;letter-spacing:1px;">AIRREV.IO</p>
          <h1 style="margin:8px 0 4px;color:white;font-size:22px;">Investment Property Report</h1>
          <p style="margin:0;color:#94A3B8;font-size:14px;">{address}</p>
        </td></tr>

        <!-- Recommendation Banner -->
        <tr><td style="background:{rec_color};padding:16px 32px;">
          <p style="margin:0;color:white;font-size:12px;opacity:0.85;">RECOMMENDATION</p>
          <p style="margin:4px 0 0;color:white;font-size:20px;font-weight:700;">{rec} &nbsp;·&nbsp; Best as {strategy}</p>
        </td></tr>

        <!-- Insight -->
        <tr><td style="padding:24px 32px;">
          <p style="margin:0 0 8px;color:#64748B;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">Key Insight</p>
          <p style="margin:0;color:#0F172A;font-size:15px;line-height:1.6;">{insight}</p>
        </td></tr>

        <!-- PDF Notice -->
        <tr><td style="padding:0 32px 24px;">
          <div style="background:#F1F5F9;border-radius:8px;padding:16px;">
            <p style="margin:0;color:#475569;font-size:14px;">📎 Your full investment report is attached as a PDF — includes complete LTR/STR analysis, mortgage breakdown, and nearby Airbnb comps.</p>
          </div>
        </td></tr>

        <!-- Footer -->
        <tr><td style="border-top:1px solid #E2E8F0;padding:20px 32px;">
          <p style="margin:0;color:#94A3B8;font-size:12px;">MLS® {mls_number} · Generated {datetime.now().strftime('%B %d, %Y')} · AirRev.io</p>
          <p style="margin:4px 0 0;color:#CBD5E1;font-size:11px;">This report is for informational purposes only and does not constitute financial advice.</p>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body>
</html>
"""


def _creb_report_email_html(month_name: str, community: str, market: dict) -> str:
    benchmark = market.get("market_summary", {}).get("benchmark_price", 0)
    yoy = market.get("market_summary", {}).get("benchmark_price_yoy_change", 0)
    condition = market.get("market_summary", {}).get("market_condition", "")

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#F8FAFC;">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center" style="padding:32px 16px;">
      <table width="600" cellpadding="0" cellspacing="0" style="background:white;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">

        <tr><td style="background:#0F172A;padding:28px 32px;">
          <p style="margin:0;color:#2563EB;font-size:12px;font-weight:700;letter-spacing:1px;">AIRREV.IO</p>
          <h1 style="margin:8px 0 4px;color:white;font-size:22px;">{community} Market Report</h1>
          <p style="margin:0;color:#94A3B8;font-size:14px;">{month_name}</p>
        </td></tr>

        <tr><td style="padding:24px 32px;">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="text-align:center;padding:12px;">
                <p style="margin:0;color:#64748B;font-size:11px;text-transform:uppercase;">Benchmark Price</p>
                <p style="margin:4px 0 0;color:#0F172A;font-size:22px;font-weight:700;">C${benchmark:,.0f}</p>
              </td>
              <td style="text-align:center;padding:12px;border-left:1px solid #E2E8F0;">
                <p style="margin:0;color:#64748B;font-size:11px;text-transform:uppercase;">YoY Change</p>
                <p style="margin:4px 0 0;color:#10B981;font-size:22px;font-weight:700;">+{yoy*100:.1f}%</p>
              </td>
              <td style="text-align:center;padding:12px;border-left:1px solid #E2E8F0;">
                <p style="margin:0;color:#64748B;font-size:11px;text-transform:uppercase;">Market</p>
                <p style="margin:4px 0 0;color:#F59E0B;font-size:18px;font-weight:700;">{condition}</p>
              </td>
            </tr>
          </table>
        </td></tr>

        <tr><td style="padding:0 32px 24px;">
          <div style="background:#F1F5F9;border-radius:8px;padding:16px;">
            <p style="margin:0;color:#475569;font-size:14px;">📎 Full market report attached — includes sales by property type, rental market data, and investment metrics.</p>
          </div>
        </td></tr>

        <tr><td style="border-top:1px solid #E2E8F0;padding:20px 32px;">
          <p style="margin:0;color:#94A3B8;font-size:12px;">{month_name} · {community} · AirRev.io · Data: CREB®</p>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body>
</html>
"""


# ── Email sender ───────────────────────────────────────────────

class EmailService:

    def __init__(self):
        self.provider = getattr(settings, "EMAIL_PROVIDER", "resend")
        self.from_email = getattr(settings, "EMAIL_FROM", "reports@airrev.io")
        self.from_name = getattr(settings, "EMAIL_FROM_NAME", "AirRev.io Reports")

    @property
    def enabled(self) -> bool:
        if self.provider == "resend":
            return bool(getattr(settings, "RESEND_API_KEY", ""))
        if self.provider == "sendgrid":
            return bool(getattr(settings, "SENDGRID_API_KEY", ""))
        if self.provider == "smtp":
            return bool(getattr(settings, "SMTP_HOST", ""))
        return False

    async def send_property_report(
        self,
        to_email: str,
        address: str,
        mls_number: str,
        summary: dict,
        pdf_bytes: bytes,
    ) -> bool:
        """Send property investment report with PDF attachment."""
        subject = f"AirRev Report: {address} — {summary.get('recommendation', 'Analysis')}"
        html_body = _property_report_email_html(address, summary, mls_number)
        filename = f"AirRev_{mls_number}_{datetime.now().strftime('%Y%m%d')}.pdf"

        return await self._send(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            pdf_bytes=pdf_bytes,
            pdf_filename=filename,
        )

    async def send_creb_report(
        self,
        to_email: str,
        month_name: str,
        community: str,
        report_data: dict,
        pdf_bytes: bytes,
    ) -> bool:
        """Send CREB monthly market report with PDF attachment."""
        subject = f"AirRev: {community} Market Report — {month_name}"
        html_body = _creb_report_email_html(month_name, community, report_data)
        filename = f"AirRev_CREB_{community.replace(' ', '')}_{month_name.replace(' ', '')}.pdf"

        return await self._send(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            pdf_bytes=pdf_bytes,
            pdf_filename=filename,
        )

    async def _send(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        pdf_bytes: Optional[bytes] = None,
        pdf_filename: str = "report.pdf",
    ) -> bool:
        if not self.enabled:
            logger.warning("Email not configured — set EMAIL_PROVIDER + credentials in .env")
            return False

        if self.provider == "resend":
            return await self._send_resend(to_email, subject, html_body, pdf_bytes, pdf_filename)
        elif self.provider == "sendgrid":
            return await self._send_sendgrid(to_email, subject, html_body, pdf_bytes, pdf_filename)
        else:
            return self._send_smtp(to_email, subject, html_body, pdf_bytes, pdf_filename)

    async def _send_resend(self, to, subject, html, pdf_bytes, filename) -> bool:
        """
        Resend API — recommended.
        https://resend.com/docs/api-reference/emails/send-email
        Free tier: 3,000 emails/month, 100/day
        """
        import base64

        payload = {
            "from": f"{self.from_name} <{self.from_email}>",
            "to": [to],
            "subject": subject,
            "html": html,
        }

        if pdf_bytes:
            payload["attachments"] = [{
                "filename": filename,
                "content": base64.b64encode(pdf_bytes).decode(),
            }]

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.post(
                    "https://api.resend.com/emails",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {getattr(settings, 'RESEND_API_KEY', '')}",
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
                logger.info(f"Email sent via Resend to {to}: {subject}")
                return True
            except Exception as e:
                logger.error(f"Resend email failed: {e}")
                return False

    async def _send_sendgrid(self, to, subject, html, pdf_bytes, filename) -> bool:
        """SendGrid API fallback."""
        import base64

        payload = {
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": self.from_email, "name": self.from_name},
            "subject": subject,
            "content": [{"type": "text/html", "value": html}],
        }
        if pdf_bytes:
            payload["attachments"] = [{
                "content": base64.b64encode(pdf_bytes).decode(),
                "type": "application/pdf",
                "filename": filename,
                "disposition": "attachment",
            }]

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {getattr(settings, 'SENDGRID_API_KEY', '')}",
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
                logger.info(f"Email sent via SendGrid to {to}")
                return True
            except Exception as e:
                logger.error(f"SendGrid email failed: {e}")
                return False

    def _send_smtp(self, to, subject, html, pdf_bytes, filename) -> bool:
        """SMTP fallback (Gmail, etc.)"""
        try:
            msg = MIMEMultipart("mixed")
            msg["From"] = f"{self.from_name} <{self.from_email}>"
            msg["To"] = to
            msg["Subject"] = subject
            msg.attach(MIMEText(html, "html"))

            if pdf_bytes:
                part = MIMEBase("application", "pdf")
                part.set_payload(pdf_bytes)
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f"attachment; filename={filename}")
                msg.attach(part)

            host = getattr(settings, "SMTP_HOST", "smtp.gmail.com")
            port = int(getattr(settings, "SMTP_PORT", 587))
            user = getattr(settings, "SMTP_USER", "")
            password = getattr(settings, "SMTP_PASSWORD", "")

            with smtplib.SMTP(host, port) as server:
                server.starttls()
                server.login(user, password)
                server.send_message(msg)

            logger.info(f"Email sent via SMTP to {to}")
            return True
        except Exception as e:
            logger.error(f"SMTP email failed: {e}")
            return False


# Singleton
email_service = EmailService()
