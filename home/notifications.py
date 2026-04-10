# home/notifications.py
"""
All email and SMS notifications for lead events.

Functions are safe to call even if SendGrid / Twilio is not configured —
they catch exceptions and log rather than raising.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, EmailMessage
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

# Physical mailing address — required by CAN-SPAM / Google guidelines
COMPANY_ADDRESS = "Garage Lions LLC, 123 Main Street, Los Angeles, CA 90001"  # ← update with real address


# ---------------------------------------------------------------------------
# SMS helper
# ---------------------------------------------------------------------------

def _send_sms(to_number: str, body: str) -> bool:
    """Send an SMS via Twilio. Returns True on success, False otherwise."""
    if not to_number:
        return False

    sid = getattr(settings, "TWILIO_ACCOUNT_SID", "")
    token = getattr(settings, "TWILIO_AUTH_TOKEN", "")
    from_number = getattr(settings, "TWILIO_FROM_NUMBER", "")

    if not (sid and token and from_number):
        logger.debug("Twilio not configured — skipping SMS to %s", to_number)
        return False

    try:
        from twilio.rest import Client
    except ImportError:
        logger.warning("twilio package not installed — SMS skipped")
        return False

    # Normalise to E.164
    digits = "".join(c for c in to_number if c.isdigit())
    if len(digits) == 10:
        digits = f"+1{digits}"
    elif len(digits) == 11 and digits.startswith("1"):
        digits = f"+{digits}"
    else:
        logger.warning("Cannot normalise phone number '%s' to E.164 — SMS skipped", to_number)
        return False

    try:
        client = Client(sid, token)
        client.messages.create(body=body, from_=from_number, to=digits)
        return True
    except Exception as exc:
        logger.error("Twilio SMS failed to %s: %s", digits, exc)
        return False


# ---------------------------------------------------------------------------
# Customer confirmation email
# ---------------------------------------------------------------------------

def notify_new_lead_to_customer(lead):
    """
    Send the customer an HTML confirmation email immediately after they submit
    the consultation form. Edit the template at:
        templates/emails/customer_confirmation.html
    """
    if not lead.email:
        return

    first = lead.first_name or "there"
    services = ", ".join(lead.consultation_types) if lead.consultation_types else "Garage services"

    from_email = settings.DEFAULT_FROM_EMAIL
    if lead.sales_point and lead.sales_point.from_email:
        from_email = lead.sales_point.from_email

    subject = "Your Garage Lions Estimate Request — We'll Be in Touch Soon!"

    context = {
        "lead": lead,
        "first": first,
        "services": services,
    }

    html_body = render_to_string("emails/customer_confirmation.html", context)

    text_body = (
        f"Hi {first},\n\n"
        f"Thank you for reaching out to Garage Lions! We have received your consultation "
        f"request and our team is already reviewing it.\n\n"
        f"One of our specialists will contact you shortly to discuss your project "
        f"and provide your FREE estimate.\n\n"
        f"Name: {lead.first_name} {lead.last_name}\n"
        f"Phone: {lead.phone}\n"
        f"ZIP: {lead.zip_code}\n"
        f"Services: {services}\n"
    )
    if lead.message:
        text_body += f"\nYour Message:\n{lead.message}\n"
    text_body += "\nBest regards,\nThe Garage Lions Team\nwww.garagelions.com\n"

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=from_email,
            to=[lead.email],
            reply_to=[from_email],
        )
        msg.attach_alternative(html_body, "text/html")
        # Google / RFC 8058 required headers for transactional email
        msg.extra_headers = {
            "List-Unsubscribe": f"<mailto:leads@garagelions.com?subject=unsubscribe>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            "X-Mailer": "Garage Lions CRM",
        }
        msg.send(fail_silently=False)
    except Exception as exc:
        logger.error("Customer confirmation email failed for lead #%s: %s", lead.pk, exc)


# ---------------------------------------------------------------------------
# Salesperson notification (email + SMS)
# ---------------------------------------------------------------------------

def notify_new_lead_to_salesperson(lead):
    """
    Notify the assigned salesperson about a new lead.
    Respects their notify_new_lead_email / notify_new_lead_sms preferences.
    Also CC's the location manager when the assigned user is a salesperson.
    """
    assigned = lead.assigned_user
    if not assigned:
        return

    try:
        profile = assigned.profile
    except Exception:
        profile = None

    send_email = getattr(profile, "notify_new_lead_email", True)
    send_sms = getattr(profile, "notify_new_lead_sms", False)
    salesperson_email = (getattr(profile, "display_email", None) if profile else None) or assigned.email
    salesperson_phone = getattr(profile, "display_phone", None) if profile else None

    services_display = ", ".join(lead.consultation_types) if lead.consultation_types else "Not specified"
    location_text = str(lead.sales_point) if lead.sales_point else "Not matched"
    city_text = str(lead.service_city) if lead.service_city else "Not matched"
    crm_url = f"https://garagelions.com/sales/leads/{lead.pk}/"

    # ── Email ──
    if send_email and salesperson_email:
        subject = f"New Lead Assigned: {lead.first_name} {lead.last_name} — {location_text}"

        text_body = (
            f"Hi {assigned.get_short_name()},\n\n"
            f"A new consultation request has been assigned to you. "
            f"Please reach out to the customer as soon as possible!\n\n"
            f"LEAD DETAILS\n"
            f"{'─'*40}\n"
            f"Name:         {lead.first_name} {lead.last_name}\n"
            f"Email:        {lead.email}\n"
            f"Phone:        {lead.phone}\n"
            f"ZIP Code:     {lead.zip_code}\n"
            f"Location:     {location_text}\n"
            f"Service City: {city_text}\n"
            f"Services:     {services_display}\n\n"
            f"Message:\n{lead.message or '(no message)'}\n\n"
            f"View in CRM: {crm_url}\n\n"
            f"— Garage Lions CRM\n"
        )

        html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif;color:#333;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;padding:30px 0;">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.1);">

      <!-- Header -->
      <tr>
        <td style="background:#1a1a2e;padding:28px 32px;">
          <h1 style="margin:0;color:#fff;font-size:20px;">New Lead Assigned to You</h1>
          <span style="display:inline-block;margin-top:8px;background:#e63946;color:#fff;padding:4px 14px;border-radius:20px;font-size:13px;font-weight:bold;">ACTION REQUIRED</span>
        </td>
      </tr>

      <!-- Body -->
      <tr>
        <td style="padding:28px 32px;">
          <p style="font-size:16px;">Hi <strong>{assigned.get_short_name()}</strong>,</p>
          <p>A new customer has submitted a consultation request and it has been assigned to you.
          <strong style="color:#e63946;">Please contact them as soon as possible.</strong></p>

          <!-- Lead details table -->
          <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e0e0e0;border-radius:6px;overflow:hidden;margin:16px 0;font-size:14px;">
            <tr style="background:#1a1a2e;">
              <td colspan="2" style="padding:10px 16px;color:#fff;font-weight:bold;font-size:13px;letter-spacing:.5px;">CUSTOMER DETAILS</td>
            </tr>
            <tr style="background:#fafafa;">
              <td style="padding:10px 16px;font-weight:bold;color:#555;width:130px;">Name</td>
              <td style="padding:10px 16px;"><strong>{lead.first_name} {lead.last_name}</strong></td>
            </tr>
            <tr>
              <td style="padding:10px 16px;font-weight:bold;color:#555;">Email</td>
              <td style="padding:10px 16px;"><a href="mailto:{lead.email}" style="color:#1a1a2e;">{lead.email}</a></td>
            </tr>
            <tr style="background:#fafafa;">
              <td style="padding:10px 16px;font-weight:bold;color:#555;">Phone</td>
              <td style="padding:10px 16px;"><a href="tel:{lead.phone}" style="color:#1a1a2e;font-size:15px;font-weight:bold;">{lead.phone}</a></td>
            </tr>
            <tr>
              <td style="padding:10px 16px;font-weight:bold;color:#555;">ZIP Code</td>
              <td style="padding:10px 16px;">{lead.zip_code}</td>
            </tr>
            <tr style="background:#fafafa;">
              <td style="padding:10px 16px;font-weight:bold;color:#555;">Location</td>
              <td style="padding:10px 16px;">{location_text}</td>
            </tr>
            <tr>
              <td style="padding:10px 16px;font-weight:bold;color:#555;">Service City</td>
              <td style="padding:10px 16px;">{city_text}</td>
            </tr>
            <tr style="background:#fafafa;">
              <td style="padding:10px 16px;font-weight:bold;color:#555;">Services</td>
              <td style="padding:10px 16px;">{services_display}</td>
            </tr>
          </table>
"""

        if lead.message:
            html_body += f"""
          <p style="font-weight:bold;margin-bottom:8px;">Customer Message</p>
          <p style="background:#fffbf0;border-left:4px solid #ffc107;padding:14px 16px;border-radius:4px;font-size:14px;line-height:1.7;">{lead.message}</p>
"""

        html_body += f"""
          <p style="margin-top:28px;text-align:center;">
            <a href="{crm_url}"
               style="display:inline-block;background:#e63946;color:#fff;padding:14px 32px;
                      text-decoration:none;border-radius:5px;font-weight:bold;font-size:15px;">
              View Lead in CRM &rarr;
            </a>
          </p>
        </td>
      </tr>

      <!-- Footer -->
      <tr>
        <td style="background:#f5f5f5;padding:14px 32px;text-align:center;font-size:12px;color:#999;">
          Garage Lions CRM &bull; Reply to this email to contact the customer directly.
        </td>
      </tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""

        # CC the location manager if assigned user is a regular salesperson
        cc_list = []
        try:
            sp_record = assigned.salesperson
            if sp_record.role == "salesperson" and sp_record.manager:
                mgr_profile = sp_record.manager.user.profile
                mgr_email = mgr_profile.display_email
                if mgr_email and mgr_email != salesperson_email:
                    cc_list.append(mgr_email)
        except Exception:
            pass

        try:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[salesperson_email],
                cc=cc_list,
                reply_to=[lead.email] if lead.email else [],
            )
            msg.attach_alternative(html_body, "text/html")
            msg.extra_headers = {
                "X-Mailer": "Garage Lions CRM",
                "Precedence": "transactional",
            }
            msg.send(fail_silently=False)
        except Exception as exc:
            logger.error("Salesperson email failed for lead #%s: %s", lead.pk, exc)

    # ── SMS ──
    if send_sms and salesperson_phone:
        sms_body = (
            f"GL NEW LEAD: {lead.first_name} {lead.last_name} | "
            f"Ph: {lead.phone} | ZIP: {lead.zip_code} | "
            f"{services_display} | CRM: {crm_url}"
        )
        _send_sms(salesperson_phone, sms_body)


# ---------------------------------------------------------------------------
# Location/admin backup email
# ---------------------------------------------------------------------------

def notify_new_lead_to_location(lead, attachment_names=None):
    """
    Send the lead details to the location's notification inbox.
    This is a plain-text admin/backup copy that always fires regardless of
    the assigned salesperson's notification preferences.
    """
    recipient = "leads@garagelions.com"
    from_email = settings.DEFAULT_FROM_EMAIL
    reply_to = []

    if lead.sales_point:
        if lead.sales_point.lead_notification_email:
            recipient = lead.sales_point.lead_notification_email
        if lead.sales_point.from_email:
            from_email = lead.sales_point.from_email
        if lead.sales_point.reply_to_email:
            reply_to = [lead.sales_point.reply_to_email]

    services_display = ", ".join(lead.consultation_types) if lead.consultation_types else ""
    assigned_text = (
        lead.assigned_user.get_full_name() or lead.assigned_user.username
    ) if lead.assigned_user else "Not assigned"

    attachments_text = ""
    if attachment_names:
        attachments_text = "\n\nAttachments:\n" + "\n".join(f"  - {n}" for n in attachment_names)

    body = (
        f"New consultation request via garagelions.com\n"
        f"{'='*50}\n"
        f"First Name:    {lead.first_name}\n"
        f"Last Name:     {lead.last_name}\n"
        f"Email:         {lead.email}\n"
        f"Phone:         {lead.phone}\n"
        f"ZIP Code:      {lead.zip_code}\n"
        f"Sales Point:   {lead.sales_point or 'Not matched'}\n"
        f"Service City:  {lead.service_city or 'Not matched'}\n"
        f"Assigned To:   {assigned_text}\n"
        f"Services:      {services_display}\n\n"
        f"Message:\n{lead.message or '(none)'}"
    ) + attachments_text

    try:
        msg = EmailMessage(
            subject=f"New Lead: {lead.first_name} {lead.last_name} — {lead.sales_point or 'Unmatched'}",
            body=body,
            from_email=from_email,
            to=[recipient],
            reply_to=reply_to,
        )
        msg.send(fail_silently=False)
    except Exception as exc:
        logger.error("Location notification email failed for lead #%s: %s", lead.pk, exc)


# ---------------------------------------------------------------------------
# Reassignment notification
# ---------------------------------------------------------------------------

def notify_lead_reassigned(lead, new_user):
    """
    Notify a salesperson when a lead is reassigned to them.
    Respects their notification preferences.
    """
    if not new_user:
        return

    try:
        profile = new_user.profile
    except Exception:
        profile = None

    send_email = getattr(profile, "notify_new_lead_email", True)
    send_sms = getattr(profile, "notify_new_lead_sms", False)
    salesperson_email = (getattr(profile, "display_email", None) if profile else None) or new_user.email
    salesperson_phone = getattr(profile, "display_phone", None) if profile else None

    services_display = ", ".join(lead.consultation_types) if lead.consultation_types else "Not specified"
    crm_url = f"https://garagelions.com/sales/leads/{lead.pk}/"

    if send_email and salesperson_email:
        subject = f"Lead Reassigned to You: {lead.first_name} {lead.last_name}"
        body = (
            f"Hi {new_user.get_short_name()},\n\n"
            f"The following lead has been reassigned to you.\n\n"
            f"Name:     {lead.first_name} {lead.last_name}\n"
            f"Email:    {lead.email}\n"
            f"Phone:    {lead.phone}\n"
            f"ZIP:      {lead.zip_code}\n"
            f"Services: {services_display}\n"
            f"Status:   {lead.get_status_display()}\n\n"
            f"View in CRM: {crm_url}\n\n"
            f"— Garage Lions CRM\n"
        )
        try:
            EmailMessage(
                subject=subject,
                body=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[salesperson_email],
                reply_to=[lead.email] if lead.email else [],
            ).send(fail_silently=False)
        except Exception as exc:
            logger.error("Reassignment email failed for lead #%s: %s", lead.pk, exc)

    if send_sms and salesperson_phone:
        sms_body = (
            f"GL LEAD REASSIGNED to you: {lead.first_name} {lead.last_name} | "
            f"{lead.phone} | {lead.zip_code} | CRM: {crm_url}"
        )
        _send_sms(salesperson_phone, sms_body)