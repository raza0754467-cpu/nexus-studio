import hashlib
import json
import re
import secrets
import smtplib
import socket
import time
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import httpx
from config_manager import DATA_DIR, load_config

USERS_FILE = DATA_DIR / "users.json"
SESSIONS_FILE = DATA_DIR / "sessions.json"
OTPS_FILE = DATA_DIR / "otps.json"

FREE_VIDEO_LIMIT = 1
OTP_TTL_SECONDS = 600  # 10 minutes

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]{2,64}@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,24}$")

# Comprehensive blocklist of fake / disposable / temporary email providers
DISPOSABLE_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "guerrillamail.net", "guerrillamail.org",
    "sharklasers.com", "grr.la", "pokemail.net", "spam4.me", "10minutemail.com",
    "10minutemail.net", "tempmail.com", "temp-mail.org", "temp-mail.io", "tmpmail.org",
    "tmpmail.net", "yopmail.com", "yopmail.fr", "yopmail.net", "throwaway.email",
    "throwawaymail.com", "trashmail.com", "trashmail.net", "trashmail.me", "getnada.com",
    "nada.email", "dispostable.com", "maildrop.cc", "fakeinbox.com", "mohmal.com",
    "emailondeck.com", "mintemail.com", "mailnesia.com", "burnermail.io", "tempail.com",
    "inboxbear.com", "33mail.com", "getairmail.com", "mailcatch.com", "mytemp.email",
    "dropmail.me", "moakt.com", "tempr.email", "discard.email", "wegwerfmail.de",
    "spamgourmet.com", "mailinator2.com", "binkmail.com", "bobmail.info", "chammy.info",
    "devnullmail.com", "dodgeit.com", "e4ward.com", "gishpuppy.com", "haltospam.com",
    "jetable.org", "kasmail.com", "meltmail.com", "mt2014.com", "no-spam.ws",
    "nospam.ze.tc", "owlpic.com", "pookmail.com", "shortmail.net", "sneakemail.com",
    "sogetthis.com", "soodonims.com", "spambox.us", "spamcero.com", "spamex.com",
    "spamfree24.org", "spamherelots.com", "spamhole.com", "spaml.com", "spammotel.com",
    "spamtroll.net", "tempinbox.com", "tempmailaddress.com", "thankyou2010.com",
    "thisisnotmyrealemail.com", "tmailinator.com", "tradermail.info", "turual.com",
    "twinmail.de", "upliftnow.com", "venompen.com", "veryrealemail.com", "viditag.com",
    "wh4f.org", "willselfdestruct.com", "zippymail.info", "example.com", "test.com",
    "fake.com", "mail.tm", "guerrillamailblock.com", "1secmail.com", "1secmail.org",
    "1secmail.net", "wwjmp.com", "esiix.com", "xojxe.com", "yoggm.com", "internxt.com",
}


def _load_json(path: Path) -> Dict[str, Any]:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def _save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000).hex()


def validate_real_email(email: str) -> str:
    """
    Strictly validates email format, blocks disposable/temp-mail domains,
    and checks DNS resolution so fake domains cannot register!
    """
    email_key = (email or "").strip().lower()
    if not EMAIL_RE.match(email_key):
        raise ValueError("Please enter a valid real email address.")
    domain = email_key.split("@", 1)[1]
    if domain in DISPOSABLE_DOMAINS or any(domain.endswith("." + d) for d in DISPOSABLE_DOMAINS):
        raise ValueError("Temporary or disposable email addresses are not allowed. Please use a real email (e.g., Gmail, Outlook, Yahoo, or your domain).")
    # Check if domain exists in DNS (fast check)
    try:
        socket.getaddrinfo(domain, None)
    except Exception:
        raise ValueError("This email domain does not appear to be valid. Please use a real email address.")
    return email_key


def is_smtp_configured() -> bool:
    cfg = load_config()
    return bool(cfg.get("smtp_user") and cfg.get("smtp_pass"))


def _send_otp_email_smtp(to_email: str, code: str) -> None:
    cfg = load_config()
    host = cfg.get("smtp_host") or "smtp.gmail.com"
    port = int(cfg.get("smtp_port") or 587)
    user = cfg.get("smtp_user") or ""
    pw = cfg.get("smtp_pass") or ""
    sender = cfg.get("smtp_from") or user

    if not user or not pw:
        raise RuntimeError("Email OTP delivery is not configured yet. Please add SMTP credentials in Admin Settings (or sign in with Google).")

    msg = EmailMessage()
    msg["Subject"] = f"{code} is your NEXUS verification code"
    msg["From"] = f"NEXUS Studio <{sender}>"
    msg["To"] = to_email
    msg.set_content(
        f"Your NEXUS verification code is: {code}\n\n"
        f"This code expires in 10 minutes. If you didn't request this, you can safely ignore this email."
    )
    msg.add_alternative(
        f"""
        <div style="font-family:Inter,Arial,sans-serif;max-width:480px;margin:0 auto;padding:28px;border:1px solid #e5e7eb;border-radius:16px;background:#ffffff;">
          <div style="font-weight:800;font-size:18px;letter-spacing:-0.02em;color:#0b0f19;margin-bottom:14px;">NEXUS</div>
          <h2 style="font-size:20px;margin:0 0 10px;color:#0b0f19;">Verify your email address</h2>
          <p style="font-size:14px;color:#526071;line-height:1.6;">Enter this 6-digit code to finish creating your NEXUS account:</p>
          <div style="font-size:32px;font-weight:800;letter-spacing:8px;text-align:center;padding:18px;margin:20px 0;background:#f8fafc;border:1px solid #e5e7eb;border-radius:12px;color:#2563eb;">{code}</div>
          <p style="font-size:12px;color:#8a95a5;">This code expires in 10 minutes. Never share it with anyone.</p>
        </div>
        """,
        subtype="html",
    )

    with smtplib.SMTP(host, port, timeout=15) as srv:
        srv.ehlo()
        srv.starttls()
        srv.ehlo()
        srv.login(user, pw)
        srv.send_message(msg)


def request_email_otp(email: str) -> Dict[str, Any]:
    email_key = validate_real_email(email)
    users = _load_json(USERS_FILE)
    if email_key in users:
        raise ValueError("An account with this email already exists. Please sign in.")

    otps = _load_json(OTPS_FILE)
    existing = otps.get(email_key)
    now = time.time()
    if existing and (now - float(existing.get("sent_at", 0))) < 25:
        raise ValueError("Please wait a few seconds before requesting another OTP code.")

    code = f"{secrets.randbelow(900000) + 100000}"
    _send_otp_email_smtp(email_key, code)

    otps[email_key] = {
        "code_hash": hashlib.sha256(code.encode("utf-8")).hexdigest(),
        "sent_at": now,
        "expires_at": now + OTP_TTL_SECONDS,
        "attempts": 0,
    }
    _save_json(OTPS_FILE, otps)
    return {"ok": True, "message": f"6-digit verification code sent to {email_key}. Check your inbox or spam folder."}


def verify_email_otp(email: str, code: str) -> bool:
    email_key = (email or "").strip().lower()
    clean_code = re.sub(r"\D", "", code or "")
    if len(clean_code) != 6:
        raise ValueError("Please enter the 6-digit OTP code sent to your email.")

    otps = _load_json(OTPS_FILE)
    rec = otps.get(email_key)
    if not rec:
        raise ValueError("No active verification code found. Please click 'Send OTP' first.")
    if time.time() > float(rec.get("expires_at", 0)):
        del otps[email_key]
        _save_json(OTPS_FILE, otps)
        raise ValueError("Verification code expired. Please request a new OTP.")
    if int(rec.get("attempts", 0)) >= 5:
        del otps[email_key]
        _save_json(OTPS_FILE, otps)
        raise ValueError("Too many wrong attempts. Please request a fresh OTP code.")

    if hashlib.sha256(clean_code.encode("utf-8")).hexdigest() != rec["code_hash"]:
        rec["attempts"] = int(rec.get("attempts", 0)) + 1
        otps[email_key] = rec
        _save_json(OTPS_FILE, otps)
        raise ValueError("Incorrect OTP code. Please double-check your email.")

    del otps[email_key]
    _save_json(OTPS_FILE, otps)
    return True


def _public_user(u: Dict[str, Any]) -> Dict[str, Any]:
    name = u.get("name", "User")
    parts = [p for p in name.strip().split() if p]
    initials = (parts[0][0] + (parts[1][0] if len(parts) > 1 else parts[0][1:2])).upper() if parts else "U"
    plan = (u.get("plan") or "free").lower()
    videos_used = int(u.get("videos_used") or 0)
    is_paid = plan in ("pro", "plus", "agency", "studio", "owner")
    return {
        "id": u.get("id"),
        "name": name,
        "email": u.get("email"),
        "plan": plan,
        "initials": initials[:2],
        "email_verified": bool(u.get("email_verified", False)),
        "auth_provider": u.get("auth_provider", "email"),
        "videos_used": videos_used,
        "free_videos_remaining": None if is_paid else max(0, FREE_VIDEO_LIMIT - videos_used),
        "created_at": u.get("created_at", ""),
    }


def register_user(name: str, email: str, password: str, otp_code: str = "") -> Dict[str, Any]:
    name = name.strip()
    if len(name) < 2:
        raise ValueError("Please enter your full name (at least 2 characters).")
    email_key = validate_real_email(email)
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")

    users = _load_json(USERS_FILE)
    if email_key in users:
        raise ValueError("An account with this email already exists. Please sign in.")

    verified = False
    if is_smtp_configured():
        verify_email_otp(email_key, otp_code)
        verified = True

    salt = secrets.token_hex(16)
    uid = "usr_" + secrets.token_hex(6)
    user = {
        "id": uid,
        "name": name,
        "email": email_key,
        "salt": salt,
        "pw_hash": _hash_password(password, salt),
        "plan": "free",
        "email_verified": verified,
        "auth_provider": "email",
        "videos_used": 0,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    users[email_key] = user
    _save_json(USERS_FILE, users)

    token = secrets.token_urlsafe(32)
    sessions = _load_json(SESSIONS_FILE)
    sessions[token] = email_key
    _save_json(SESSIONS_FILE, sessions)

    return {"token": token, "user": _public_user(user)}


async def login_with_google_credential(id_token: str) -> Dict[str, Any]:
    """
    Verifies a real Google Identity Services ID token with Google's official tokeninfo endpoint,
    guarantees verified Google email, and signs in or creates the user cleanly!
    """
    cfg = load_config()
    expected_aud = (cfg.get("google_client_id") or "").strip()
    if not expected_aud:
        raise ValueError("Google Sign-In is not configured yet. Add GOOGLE_CLIENT_ID in environment settings.")
    if not id_token or len(id_token) < 40:
        raise ValueError("Invalid Google credential.")

    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get("https://oauth2.googleapis.com/tokeninfo", params={"id_token": id_token})
        if r.status_code != 200:
            raise ValueError("Could not verify Google sign-in token. Please try again.")
        info = r.json()

    if info.get("aud") != expected_aud:
        raise ValueError("Google token audience mismatch.")
    if str(info.get("email_verified", "")).lower() != "true":
        raise ValueError("Your Google email must be verified to sign in.")

    email_key = validate_real_email(info.get("email", ""))
    name = (info.get("name") or email_key.split("@")[0]).strip()

    users = _load_json(USERS_FILE)
    user = users.get(email_key)
    if not user:
        user = {
            "id": "usr_" + secrets.token_hex(6),
            "name": name,
            "email": email_key,
            "salt": secrets.token_hex(16),
            "pw_hash": "",
            "plan": "free",
            "email_verified": True,
            "auth_provider": "google",
            "videos_used": 0,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        users[email_key] = user
        _save_json(USERS_FILE, users)

    token = secrets.token_urlsafe(32)
    sessions = _load_json(SESSIONS_FILE)
    sessions[token] = email_key
    _save_json(SESSIONS_FILE, sessions)
    return {"token": token, "user": _public_user(user)}


def login_user(email: str, password: str) -> Dict[str, Any]:
    email_key = (email or "").strip().lower()
    users = _load_json(USERS_FILE)
    user = users.get(email_key)
    if not user:
        raise ValueError("Invalid email or password.")
    if not user.get("pw_hash"):
        raise ValueError("This account uses Google Sign-In. Please click 'Continue with Google'.")
    if _hash_password(password, user["salt"]) != user["pw_hash"]:
        raise ValueError("Invalid email or password.")

    token = secrets.token_urlsafe(32)
    sessions = _load_json(SESSIONS_FILE)
    sessions[token] = email_key
    _save_json(SESSIONS_FILE, sessions)

    return {"token": token, "user": _public_user(user)}


def get_user_by_token(token: Optional[str]) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    sessions = _load_json(SESSIONS_FILE)
    email_key = sessions.get(token)
    if not email_key:
        return None
    users = _load_json(USERS_FILE)
    user = users.get(email_key)
    return _public_user(user) if user else None


def logout_token(token: Optional[str]) -> None:
    if not token:
        return
    sessions = _load_json(SESSIONS_FILE)
    if token in sessions:
        del sessions[token]
        _save_json(SESSIONS_FILE, sessions)


def update_user_plan(token: Optional[str], plan_id: str) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    sessions = _load_json(SESSIONS_FILE)
    email_key = sessions.get(token)
    if not email_key:
        return None
    users = _load_json(USERS_FILE)
    user = users.get(email_key)
    if not user:
        return None
    user["plan"] = plan_id.lower()
    users[email_key] = user
    _save_json(USERS_FILE, users)
    return _public_user(user)


def check_video_quota(token: Optional[str]) -> Tuple[bool, int, str]:
    """
    Strictly enforces:
    1. Video generation REQUIRES signing in with a real account (HTTP 401 if guest!).
    2. Free ($0) accounts get 1 complete Full HD trial video; after 1 video returns HTTP 402!
    3. Creator Pro / Agency Studio / Owner accounts get unlimited videos.
    """
    if not token:
        return False, 401, "Please sign in with your real email or Google account to create your free HD video."
    sessions = _load_json(SESSIONS_FILE)
    email_key = sessions.get(token)
    if not email_key:
        return False, 401, "Your session expired. Please sign in again to create videos."
    users = _load_json(USERS_FILE)
    user = users.get(email_key)
    if not user:
        return False, 401, "Please sign in to create videos."

    plan = (user.get("plan") or "free").lower()
    if plan in ("pro", "plus", "agency", "studio", "owner"):
        return True, 200, ""
    used = int(user.get("videos_used") or 0)
    if used >= FREE_VIDEO_LIMIT:
        return False, 402, "You have used your 1 Free trial video. Upgrade to Creator Pro ($19/mo) or Agency Studio ($49/mo) for unlimited Full HD videos."
    return True, 200, ""


def record_video_usage(token: Optional[str]) -> None:
    if not token:
        return
    sessions = _load_json(SESSIONS_FILE)
    email_key = sessions.get(token)
    if not email_key:
        return
    users = _load_json(USERS_FILE)
    user = users.get(email_key)
    if user:
        user["videos_used"] = int(user.get("videos_used") or 0) + 1
        users[email_key] = user
        _save_json(USERS_FILE, users)
