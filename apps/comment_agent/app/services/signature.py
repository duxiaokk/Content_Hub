import hashlib
import hmac


def verify_hmac_signature(raw_body: bytes, secret: str, signature: str) -> bool:
    if not signature.startswith("sha256="):
        return False

    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    provided = signature.removeprefix("sha256=")
    return hmac.compare_digest(expected, provided)
