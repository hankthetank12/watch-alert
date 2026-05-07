import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def _get_env(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        raise RuntimeError(f"Environment variable {key!r} is not set")
    return val


def _build_message(new_by_site: dict[str, list[dict]], from_addr: str, to_addr: str) -> MIMEMultipart:
    """
    new_by_site: { site_name: [watch_dict, ...] }
    Only sites that have new watches should be passed in.
    """
    sites = list(new_by_site.keys())
    total = sum(len(v) for v in new_by_site.values())

    # Subject line
    if len(sites) == 1:
        site_name = sites[0]
        watches = new_by_site[site_name]
        if len(watches) == 1:
            subject = f"🆕 {site_name}: {watches[0]['title']}"
        else:
            subject = f"🆕 {site_name}: {len(watches)} new watches added"
    else:
        site_summary = ", ".join(f"{s} (+{len(new_by_site[s])})" for s in sites)
        subject = f"🆕 {total} new watches — {site_summary}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr

    # Build plain text and HTML — one section per site
    plain_sections = []
    html_sections = []

    for site_name, watches in new_by_site.items():
        # Plain text section
        plain_lines = [f"{site_name}:", "-" * len(site_name)]
        for w in watches:
            partner_tag = " [Partner listing]" if w.get("is_partner") else ""
            price_tag = f" — {w['price']}" if w.get("price") else ""
            plain_lines.append(f"  • {w['title']}{price_tag}{partner_tag}\n    {w['url']}")
        plain_sections.append("\n".join(plain_lines))

        # HTML section
        items_html = ""
        for w in watches:
            partner_tag = " <em>(Partner listing)</em>" if w.get("is_partner") else ""
            price_tag = f' <span style="color:#555;font-weight:bold">{w["price"]}</span>' if w.get("price") else ""
            items_html += f'      <li><a href="{w["url"]}">{w["title"]}</a>{price_tag}{partner_tag}</li>\n'

        html_sections.append(f"""\
  <section style="margin-bottom:24px">
    <h2 style="margin:0 0 8px;font-size:16px;border-bottom:1px solid #ddd;padding-bottom:4px">{site_name}</h2>
    <ul style="margin:0;padding-left:20px">
{items_html}    </ul>
  </section>""")

    plain_body = "\n\n".join(plain_sections)
    html_body = f"""\
<html>
  <body style="font-family:sans-serif;color:#222;max-width:600px">
    <p style="margin-bottom:16px">New watch{"es" if total > 1 else ""} just listed:</p>
{"".join(html_sections)}
  </body>
</html>"""

    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))
    return msg


def send_alert(new_by_site: dict[str, list[dict]]) -> None:
    """Send one consolidated email covering all sites that have new watches."""
    new_by_site = {k: v for k, v in new_by_site.items() if v}
    if not new_by_site:
        return

    from_addr = _get_env("GMAIL_ADDRESS")
    app_password = _get_env("GMAIL_APP_PASSWORD")
    to_addr = _get_env("ALERT_TO_EMAIL")

    msg = _build_message(new_by_site, from_addr, to_addr)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(from_addr, app_password)
            server.sendmail(from_addr, [to_addr], msg.as_string())
        total = sum(len(v) for v in new_by_site.values())
        logger.info("Alert sent to %s — %d watch(es) across %d site(s): %s",
                    to_addr, total, len(new_by_site), msg["Subject"])
    except smtplib.SMTPException as exc:
        logger.error("Failed to send email alert: %s", exc)
        raise
