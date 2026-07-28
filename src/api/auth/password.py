import re
from typing import Optional

import bcrypt
from passlib.hash import pbkdf2_sha256

# Fallback to pbkdf2_sha256 if bcrypt is acting up with newer python/library versions
# Using bcrypt directly for password hashing

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if hashed_password.startswith("$pbkdf2-sha256$"):
        try:
            return pbkdf2_sha256.verify(plain_password, hashed_password)
        except (ValueError, TypeError):
            return False

    try:
        return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())
    except (ValueError, TypeError):
        return False


def validate_password_strength(password: str) -> tuple[bool, Optional[str]]:
    if len(password) < MIN_PASSWORD_LENGTH:
        return False, f"Password must be at least {MIN_PASSWORD_LENGTH} characters long"

    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        return False, f"Password must not exceed {MAX_PASSWORD_BYTES} bytes"

    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"

    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"

    if not re.search(r"[0-9]", password):
        return False, "Password must contain at least one number"

    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False, "Password must contain at least one special character"

    return True, None
