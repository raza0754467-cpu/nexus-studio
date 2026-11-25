import hashlib
import json
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from config_manager import DATA_DIR

USERS_FILE = DATA_DIR / "users.json"
SESSIONS_FILE = DATA_DIR / "sessions.json"
GUEST_USAGE_FILE = DATA_DIR / "guest_usage.json"

FREE_VIDEO_LIMIT = 1


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
        "videos_used": videos_used,
        "free_videos_remaining": None if is_paid else max(0, FREE_VIDEO_LIMIT - videos_used),
        "created_at": u.get("created_at", ""),
    }


def register_user(name: str, email: str, password: str) -> Dict[str, Any]:
    name = name.strip()
    email_key = email.strip().lower()
    if len(name) < 2:
        raise ValueError("Please enter your full name (at least 2 characters).")
    if "@" not in email_key or "." not in email_key:
        raise ValueError("Please enter a valid email address.")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")

    users = _load_json(USERS_FILE)
    if email_key in users:
        raise ValueError("An account with this email already exists. Please sign in.")

    salt = secrets.token_hex(16)
    uid = "usr_" + secrets.token_hex(6)
    user = {
        "id": uid,
        "name": name,
        "email": email_key,
        "salt": salt,
        "pw_hash": _hash_password(password, salt),
        "plan": "free",
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
    email_key = email.strip().lower()
    users = _load_json(USERS_FILE)
    user = users.get(email_key)
    if not user:
        raise ValueError("Invalid email or password.")
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


def check_video_quota(token: Optional[str], guest_id: Optional[str] = None) -> Tuple[bool, str]:
    """
    Enforces the $0 Free Plan rule: Free users (and guests) get 1 full-quality trial video
    so they can experience NEXUS before upgrading to Creator Pro or Agency Studio.
    """
    if token:
        sessions = _load_json(SESSIONS_FILE)
        email_key = sessions.get(token)
        if email_key:
            users = _load_json(USERS_FILE)
            user = users.get(email_key)
            if user:
                plan = (user.get("plan") or "free").lower()
                if plan in ("pro", "plus", "agency", "studio", "owner"):
                    return True, ""
                used = int(user.get("videos_used") or 0)
                if used >= FREE_VIDEO_LIMIT:
                    return False, "You have used your 1 Free trial video. Upgrade to Creator Pro ($19/mo) or Agency Studio ($49/mo) for unlimited Full HD videos."
                return True, ""
    if guest_id:
        gmap = _load_json(GUEST_USAGE_FILE)
        used = int(gmap.get(guest_id, 0))
        if used >= FREE_VIDEO_LIMIT:
            return False, "Your 1 Free trial video is complete! Create an account and upgrade to Creator Pro to unlock unlimited videos."
    return True, ""


def record_video_usage(token: Optional[str], guest_id: Optional[str] = None) -> None:
    if token:
        sessions = _load_json(SESSIONS_FILE)
        email_key = sessions.get(token)
        if email_key:
            users = _load_json(USERS_FILE)
            user = users.get(email_key)
            if user:
                user["videos_used"] = int(user.get("videos_used") or 0) + 1
                users[email_key] = user
                _save_json(USERS_FILE, users)
                return
    if guest_id:
        gmap = _load_json(GUEST_USAGE_FILE)
        gmap[guest_id] = int(gmap.get(guest_id, 0)) + 1
        _save_json(GUEST_USAGE_FILE, gmap)
