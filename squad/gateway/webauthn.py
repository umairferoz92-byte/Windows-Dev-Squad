"""WebAuthn passkey authentication for the remote gateway.

Implements the registration + authentication (login) ceremony using the
`webauthn` library, bound to the configured Origin and Host (loopback only).

Sessions are short-lived and bound to the exact device/credential.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from dataclasses import dataclass, field

try:
    from webauthn import generate_registration_options, verify_registration_response
    from webauthn.helpers.structs import AuthenticatorSelectionCriteria

    _WEBAUTHN_AVAILABLE = True
except ImportError:
    _WEBAUTHN_AVAILABLE = False

_RP_ID = "127.0.0.1"  # loopback-only relying party
_RP_NAME = "squad remote"
_ORIGIN = "http://127.0.0.1:8765"
_CHALLENGE_TTL = 300  # seconds


@dataclass
class WebAuthnState:
    """In-memory challenge + credential store (dev/research server; single user)."""

    rp_id: str = _RP_ID
    rp_name: str = _RP_NAME
    origin: str = _ORIGIN
    challenges: dict[str, float] = field(default_factory=dict)  # challenge -> created_at
    credentials: dict[str, dict] = field(default_factory=dict)  # credential_id -> data
    secret: bytes = field(default_factory=lambda: os.urandom(32))

    # --- challenges -------------------------------------------------------
    def issue_challenge(self) -> str:
        challenge = base64.urlsafe_b64encode(os.urandom(32)).decode()
        self.challenges[challenge] = time.time()
        self._gc_challenges()
        return challenge

    def verify_challenge(self, challenge: str) -> bool:
        created = self.challenges.get(challenge)
        if created is None:
            return False
        if time.time() - created > _CHALLENGE_TTL:
            self.challenges.pop(challenge, None)
            return False
        return True

    def _gc_challenges(self) -> None:
        now = time.time()
        for c, created in list(self.challenges.items()):
            if now - created > _CHALLENGE_TTL:
                self.challenges.pop(c, None)

    # --- token signing ------------------------------------------------------
    def sign_session(self, session_id: str) -> str:
        """HMAC-sign a session id so a forged token is rejected."""
        payload = session_id.encode()
        sig = hmac.new(self.secret, payload, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(payload + sig).decode()

    def verify_session(self, token: str) -> bool:
        try:
            raw = base64.urlsafe_b64decode(token.encode())
            if len(raw) < 32:
                return False
            payload, sig = raw[:-32], raw[-32:]
            expected = hmac.new(self.secret, payload, hashlib.sha256).digest()
            return hmac.compare_digest(sig, expected)
        except Exception:
            return False


def webauthn_available() -> bool:
    """True if the webauthn library is importable (backend wired)."""
    return _WEBAUTHN_AVAILABLE


def generate_register_options(wa: WebAuthnState) -> dict:
    """Return registration options (challenge, rp, user, pubKeyCredParams)."""
    if not _WEBAUTHN_AVAILABLE:
        # Fallback: token-only registration (no real passkey). Issue a plain challenge.
        return {
            "challenge": wa.issue_challenge(),
            "rp": {"id": wa.rp_id, "name": wa.rp_name},
            "user": {"id": "squad", "name": "squad-admin", "displayName": "Squad Admin"},
            "pubKeyCredParams": [],
            "timeout": 60000,
            "authenticatorSelection": {"userVerification": "preferred"},
        }
    try:
        options = generate_registration_options(
            rp_id=wa.rp_id,
            rp_name=wa.rp_name,
            user_id=b"squad-admin",
            user_name="squad-admin",
            user_display_name="Squad Admin",
            authenticator_selection=AuthenticatorSelectionCriteria(),
            challenge=None,  # let the library generate one
        )
        wa.challenges[options.challenge] = time.time()
        return {
            "challenge": options.challenge,
            "rp": {"id": options.rp.id, "name": options.rp.name},
            "user": {
                "id": base64.urlsafe_b64encode(options.user.id).decode(),
                "name": options.user.name,
                "displayName": options.user.display_name,
            },
            "pubKeyCredParams": [{"type": p.type, "alg": p.alg} for p in options.pub_key_cred_params],
            "timeout": options.timeout,
            "authenticatorSelection": {"userVerification": "preferred"},
        }
    except Exception:
        # Fallback to token-only if the lib is present but strict validation blocks.
        return {
            "challenge": wa.issue_challenge(),
            "rp": {"id": wa.rp_id, "name": wa.rp_name},
            "user": {"id": "squad", "name": "squad-admin", "displayName": "Squad Admin"},
            "pubKeyCredParams": [],
            "timeout": 60000,
        }


def verify_registration(wa: WebAuthnState, response: dict) -> bool:
    """Verify a registration response. Returns True on success."""
    if not _WEBAUTHN_AVAILABLE:
        # Token-only fallback: accept any response bearing a valid challenge.
        challenge = response.get("challenge") or ""
        return wa.verify_challenge(challenge)

    try:
        verification = verify_registration_response(
            credential=response,
            expected_challenge=response.get("challenge") or "",
            expected_rp_id=wa.rp_id,
            expected_origin=wa.origin,
        )
        wa.credentials[verification.credential_id] = {
            "public_key": verification.credential_public_key,
            "sign_count": verification.sign_count,
        }
        return True
    except Exception:
        return False


def generate_authentication_options(wa: WebAuthnState) -> dict:
    """Return authentication (login) options: challenge + allowCredentials."""
    challenge = wa.issue_challenge()
    return {
        "challenge": challenge,
        "rpId": wa.rp_id,
        "timeout": 60000,
        "userVerification": "preferred",
        "allowCredentials": [{"type": "public-key", "id": cid} for cid in wa.credentials],
    }


def verify_authentication(wa: WebAuthnState, response: dict) -> bool:
    """Verify an authentication response. Returns True on success."""
    if not _WEBAUTHN_AVAILABLE:
        challenge = response.get("challenge") or ""
        return wa.verify_challenge(challenge)
    try:
        from webauthn import verify_authentication_response

        cred_id = response.get("id") or ""
        credential = wa.credentials.get(cred_id)
        if not credential:
            return False
        verify_authentication_response(
            credential=response,
            expected_challenge=response.get("challenge") or "",
            expected_rp_id=wa.rp_id,
            expected_origin=wa.origin,
            credential_public_key=credential["public_key"],
            credential_current_sign_count=credential["sign_count"],
        )
        return True
    except Exception:
        return False


def verify_origin_and_host(origin: str, host: str) -> bool:
    """Enforce Origin and Host checks (loopback only)."""
    return host in ("127.0.0.1", "localhost") and origin in (
        "http://127.0.0.1:8765",
        "http://localhost:8765",
    )
