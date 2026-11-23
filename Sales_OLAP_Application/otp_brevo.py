"""Brevo OTP delivery helpers for PharmaTrack DW."""
import hashlib
import os
import secrets
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

OTP_EXPIRY_MINUTES = 5
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_WHATSAPP_FALLBACK_DELAY_SECONDS = 120

BREVO_SMS_URL = "https://api.brevo.com/v3/transactionalSMS/send"
BREVO_WHATSAPP_URL = "https://api.brevo.com/v3/whatsapp/sendMessage"
BREVO_EMAIL_URL = "https://api.brevo.com/v3/smtp/email"


def normalize_phone(phone: str) -> str:
    """Return an international-format digit string accepted by Brevo."""
    raw = str(phone or "").strip()
    if raw.startswith("00"):
        raw = raw[2:]
    digits = "".join(character for character in raw if character.isdigit())

    # The capstone is configured for India; accept a locally entered 10-digit
    # number or trunk-prefixed 0 + 10-digit number, and add country code 91.
    if len(digits) == 10:
        digits = "91" + digits
    elif len(digits) == 11 and digits.startswith("0"):
        digits = "91" + digits[1:]

    if not 8 <= len(digits) <= 15:
        return ""
    return digits


def mask_phone(phone: str) -> str:
    """Mask a phone number for display, e.g. +91 ****2121."""
    digits = normalize_phone(phone)
    if not digits:
        return "****"
    if digits.startswith("91") and len(digits) == 12:
        return f"+91 ****{digits[-4:]}"
    return f"+{digits[:-10]} ****{digits[-4:]}" if len(digits) > 10 else f"****{digits[-4:]}"


def hash_otp(otp: str) -> str:
    """Hash an OTP for database storage."""
    return hashlib.sha256(str(otp).encode("utf-8")).hexdigest()


def mask_email(email: str) -> str:
    """Mask an email address for OTP screens without exposing the full address."""
    value = str(email or "").strip()
    if "@" not in value:
        return "***"
    local, domain = value.rsplit("@", 1)
    if not local or not domain:
        return "***"
    visible = local[:1]
    return f"{visible}{'*' * min(max(len(local) - 1, 3), 8)}@{domain}"


def missing_email_configuration() -> list[str]:
    missing = []
    if not os.environ.get("BREVO_API_KEY", "").strip():
        missing.append("BREVO_API_KEY")
    if not os.environ.get("BREVO_EMAIL_SENDER", "").strip():
        missing.append("BREVO_EMAIL_SENDER")
    return missing


def email_configuration_error() -> str:
    missing = missing_email_configuration()
    if not missing:
        return ""
    return (
        "Email OTP is unavailable until these settings are added to the local .env file: "
        + ", ".join(missing)
        + "."
    )


def is_email_configured() -> bool:
    """True when Brevo's API key and verified sender email are configured."""
    return not missing_email_configuration()


def _email_provider_error(status_code: int) -> str:
    if status_code in (401, 403):
        return "Brevo rejected the API key or sender authorization. Check the API key and verify the sender email in Brevo."
    if status_code == 402:
        return "Brevo reports an account or transactional-email credit issue. Check the account and sending limits."
    if status_code == 400:
        return "Brevo rejected the email request. Check the recipient and that BREVO_EMAIL_SENDER is a verified sender."
    if status_code == 429:
        return "Brevo rate-limited the email request. Wait before trying again."
    if status_code >= 500:
        return "Brevo is temporarily unavailable. Check its status and try again later."
    return f"Brevo could not submit the email (HTTP {status_code})."


def send_otp_email(email: str, otp_code: str, display_name: str = "") -> dict:
    """Submit a one-time sign-in code to the account's registered email."""
    import requests

    missing = missing_email_configuration()
    if missing:
        return {
            "success": False,
            "error": "Missing Brevo configuration: " + ", ".join(missing),
            "status": "not_configured",
            "channel": "email",
        }

    recipient = str(email or "").strip().lower()
    if not recipient or "@" not in recipient or recipient.startswith("@") or recipient.endswith("@"):
        return {
            "success": False,
            "error": "The account does not have a valid registered email address.",
            "status": "failed",
            "channel": "email",
        }

    sender_email = os.environ["BREVO_EMAIL_SENDER"].strip()
    sender_name = os.environ.get("BREVO_EMAIL_SENDER_NAME", "PharmaTrack DW").strip() or "PharmaTrack DW"
    greeting = f"Hello {display_name.strip()}," if display_name.strip() else "Hello,"
    subject = "Your PharmaTrack DW sign-in code"
    text_content = (
        f"{greeting}\n\nYour PharmaTrack DW sign-in code is {otp_code}. "
        f"It expires in {OTP_EXPIRY_MINUTES} minutes. If you did not request this code, ignore this email. "
        "Do not share this code with anyone."
    )
    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": recipient}],
        "subject": subject,
        "textContent": text_content,
        "tags": ["pharmatrack-otp"],
    }

    try:
        response = requests.post(
            BREVO_EMAIL_URL,
            json=payload,
            headers={
                "api-key": os.environ["BREVO_API_KEY"].strip(),
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=15,
        )
    except requests.Timeout:
        return {
            "success": False,
            "error": "Brevo did not respond before the request timed out. Check Brevo logs before requesting another code.",
            "status": "unknown",
            "channel": "email",
        }
    except requests.RequestException:
        return {
            "success": False,
            "error": "Could not connect to Brevo. Check the network and Brevo service status.",
            "status": "error",
            "channel": "email",
        }

    data = _response_json(response)
    if 200 <= response.status_code < 300:
        return {
            "success": True,
            "channel": "email",
            "message_id": str(data.get("messageId", "")),
            "status": "submitted",
            "error": None,
        }
    return {
        "success": False,
        "channel": "email",
        "error": _email_provider_error(response.status_code),
        "status": "failed",
    }


def generate_otp() -> tuple[str, str]:
    """Return a cryptographically secure 6-digit OTP and its stored hash."""
    otp = str(secrets.randbelow(900000) + 100000)
    return otp, hash_otp(otp)


def missing_sms_configuration() -> list[str]:
    missing = []
    if not os.environ.get("BREVO_API_KEY", "").strip():
        missing.append("BREVO_API_KEY")
    if not os.environ.get("BREVO_SMS_SENDER", "").strip():
        missing.append("BREVO_SMS_SENDER")
    return missing


def sms_configuration_error() -> str:
    missing = missing_sms_configuration()
    if not missing:
        return ""
    return (
        "SMS OTP sign-in is unavailable until the following settings are added "
        "to the local .env file: " + ", ".join(missing) + "."
    )


def is_brevo_configured() -> bool:
    """True only when the required Brevo SMS credentials and sender are present."""
    return not missing_sms_configuration()


def get_otp_destination(user_phone: str = "") -> str:
    """
    Return the configured owner-demo destination, or the user's own number.
    PHARMATRACK_OTP_DESTINATION must be blank for per-user production delivery.
    """
    demo_destination = os.environ.get("PHARMATRACK_OTP_DESTINATION", "").strip()
    return demo_destination or str(user_phone or "").strip()


def _response_json(response) -> dict:
    try:
        data = response.json()
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def _provider_error(status_code: int) -> str:
    if status_code in (401, 403):
        return (
            "Brevo rejected the API key, account permissions, or sender authorization. "
            "Check the Brevo account and approved sender settings."
        )
    if status_code == 402:
        return "Brevo reports an account or SMS-credit issue. Check your plan and credit balance."
    if status_code == 400:
        return (
            "Brevo rejected the message settings. Check the recipient country code, "
            "approved sender, message template, and any required Indian DLT setup."
        )
    if status_code == 429:
        return "Brevo rate-limited the request. Wait before trying again."
    if status_code >= 500:
        return "Brevo is temporarily unavailable. Check its status and try again later."
    return f"Brevo could not submit the message (HTTP {status_code})."


def _optional_webhook_url() -> str:
    """Return a status callback URL with its shared token, when configured."""
    base_url = os.environ.get("BREVO_SMS_STATUS_WEBHOOK_URL", "").strip()
    token = os.environ.get("BREVO_SMS_WEBHOOK_TOKEN", "").strip()
    if not base_url or not token:
        return ""
    try:
        parts = urlsplit(base_url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["token"] = token
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
        )
    except Exception:
        return ""


def send_otp_sms(phone: str, otp_code: str) -> dict:
    """
    Submit an OTP through Brevo Transactional SMS.
    A successful API response means submitted, not necessarily delivered.
    """
    import requests

    missing = missing_sms_configuration()
    if missing:
        return {
            "success": False,
            "error": "Missing Brevo configuration: " + ", ".join(missing),
            "status": "not_configured",
            "channel": "sms",
        }

    recipient = normalize_phone(phone)
    if not recipient:
        return {
            "success": False,
            "error": "The OTP destination phone number is missing or invalid.",
            "status": "failed",
            "channel": "sms",
        }

    sender = os.environ["BREVO_SMS_SENDER"].strip()
    api_key = os.environ["BREVO_API_KEY"].strip()
    template_id = os.environ.get("BREVO_SMS_TEMPLATE_ID", "").strip()
    payload = {
        "sender": sender,
        "recipient": recipient,
        "type": "transactional",
        "tag": "pharmatrack-otp",
    }

    if template_id:
        try:
            payload["templateId"] = int(template_id)
        except ValueError:
            return {
                "success": False,
                "error": "BREVO_SMS_TEMPLATE_ID must be a numeric Brevo template ID.",
                "status": "not_configured",
                "channel": "sms",
            }
        payload["params"] = {
            "otp": otp_code,
            "minutes": str(OTP_EXPIRY_MINUTES),
        }
    else:
        payload["content"] = (
            f"Your PharmaTrack verification code is {otp_code}. "
            f"It expires in {OTP_EXPIRY_MINUTES} minutes. Do not share it."
        )

    callback_url = _optional_webhook_url()
    if callback_url:
        payload["webUrl"] = callback_url

    try:
        response = requests.post(
            BREVO_SMS_URL,
            json=payload,
            headers={
                "api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=15,
        )
    except requests.Timeout:
        return {
            "success": False,
            "error": (
                "Brevo did not respond before the request timed out. The send status "
                "is uncertain; check Brevo logs before requesting another code."
            ),
            "status": "unknown",
            "channel": "sms",
        }
    except requests.RequestException:
        return {
            "success": False,
            "error": "Could not connect to Brevo. Check the network and Brevo service status.",
            "status": "error",
            "channel": "sms",
        }

    data = _response_json(response)
    if 200 <= response.status_code < 300:
        return {
            "success": True,
            "channel": "sms",
            "message_id": str(data.get("messageId", "")),
            "status": "submitted",
            "error": None,
        }

    return {
        "success": False,
        "channel": "sms",
        "error": _provider_error(response.status_code),
        "status": "failed",
    }


def send_otp_whatsapp(phone: str, otp_code: str) -> dict:
    """
    Submit an OTP through Brevo transactional WhatsApp.
    Requires an approved template containing {{ params.otp }} and
    {{ params.minutes }} placeholders.
    """
    import requests

    api_key = os.environ.get("BREVO_API_KEY", "").strip()
    sender_number = normalize_phone(
        os.environ.get("BREVO_WHATSAPP_SENDER_NUMBER", "")
    )
    template_id = os.environ.get("BREVO_WHATSAPP_TEMPLATE_ID", "").strip()
    recipient = normalize_phone(phone)

    if not api_key:
        missing = ["BREVO_API_KEY"]
        return {
            "success": False,
            "error": "Missing Brevo configuration: " + ", ".join(missing),
            "status": "not_configured",
            "channel": "whatsapp",
        }
    if not sender_number or not template_id:
        return {
            "success": False,
            "error": (
                "WhatsApp fallback requires BREVO_WHATSAPP_SENDER_NUMBER and "
                "an approved BREVO_WHATSAPP_TEMPLATE_ID."
            ),
            "status": "not_configured",
            "channel": "whatsapp",
        }
    if not recipient:
        return {
            "success": False,
            "error": "The OTP destination phone number is missing or invalid.",
            "status": "failed",
            "channel": "whatsapp",
        }
    try:
        numeric_template_id = int(template_id)
    except ValueError:
        return {
            "success": False,
            "error": "BREVO_WHATSAPP_TEMPLATE_ID must be a numeric template ID.",
            "status": "not_configured",
            "channel": "whatsapp",
        }

    payload = {
        "senderNumber": sender_number,
        "templateId": numeric_template_id,
        "contactNumbers": [recipient],
        "params": {
            "otp": otp_code,
            "minutes": str(OTP_EXPIRY_MINUTES),
        },
    }

    try:
        response = requests.post(
            BREVO_WHATSAPP_URL,
            json=payload,
            headers={
                "api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=15,
        )
    except requests.Timeout:
        return {
            "success": False,
            "error": "Brevo WhatsApp did not respond in time; check provider logs before retrying.",
            "status": "unknown",
            "channel": "whatsapp",
        }
    except requests.RequestException:
        return {
            "success": False,
            "error": "Could not connect to Brevo WhatsApp. Check network and account setup.",
            "status": "error",
            "channel": "whatsapp",
        }

    data = _response_json(response)
    if 200 <= response.status_code < 300:
        return {
            "success": True,
            "channel": "whatsapp",
            "message_id": str(data.get("messageId", "")),
            "status": "submitted",
            "error": None,
        }

    return {
        "success": False,
        "channel": "whatsapp",
        "error": _provider_error(response.status_code),
        "status": "failed",
    }
