"""INSITEVA account, entitlement and licensing client.

The desktop app never stores payment secrets. Supabase handles identity; a small
server/edge-function API handles entitlements and Razorpay verification.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import requests


@dataclass
class AuthSession:
    access_token: str
    refresh_token: str = ""
    user_id: str = ""
    email: str = ""
    plan: str = "free"
    expires_at: Optional[str] = None
    dataset_limit: int = 5
    datasets_used: int = 0
    founder_customer_number: Optional[int] = None

    @property
    def is_paid(self) -> bool:
        return self.plan.lower() != "free"

    @property
    def datasets_remaining(self) -> int:
        if self.dataset_limit < 0:
            return 10**9
        return max(0, self.dataset_limit - self.datasets_used)


class AuthError(RuntimeError):
    pass


class InsitevaAuthClient:
    def __init__(self, supabase_url: str | None = None, anon_key: str | None = None, api_url: str | None = None):
        self.supabase_url = (supabase_url or os.getenv("INSITEVA_SUPABASE_URL", "")).rstrip("/")
        self.anon_key = anon_key or os.getenv("INSITEVA_SUPABASE_ANON_KEY", "")
        self.api_url = (api_url or os.getenv("INSITEVA_LICENSE_API_URL", "")).rstrip("/")
        self.session: Optional[AuthSession] = None

    @property
    def configured(self) -> bool:
        return bool(self.supabase_url and self.anon_key)

    def _headers(self, token: str | None = None) -> dict[str, str]:
        h = {"apikey": self.anon_key, "Content-Type": "application/json"}
        if token:
            h["Authorization"] = f"Bearer {token}"
        return h

    def signup(self, email: str, password: str) -> str:
        self._require_configured()
        r = requests.post(
            f"{self.supabase_url}/auth/v1/signup",
            headers=self._headers(),
            json={"email": email.strip(), "password": password},
            timeout=20,
        )
        if not r.ok:
            raise AuthError(self._error_text(r))
        data = r.json()
        # Hosted Supabase projects commonly require email verification.
        if not data.get("access_token"):
            return "Account created. Check your email to verify your address, then sign in."
        self._set_session(data)
        return "Account created successfully."

    def login(self, email: str, password: str) -> AuthSession:
        self._require_configured()
        r = requests.post(
            f"{self.supabase_url}/auth/v1/token?grant_type=password",
            headers=self._headers(),
            json={"email": email.strip(), "password": password},
            timeout=20,
        )
        if not r.ok:
            raise AuthError(self._error_text(r))
        data = r.json()
        self._set_session(data)
        try:
            self.refresh_entitlement()
        except Exception:
            # Login should still succeed if entitlement service is temporarily unavailable.
            pass
        return self.session

    def reset_password(self, email: str) -> None:
        self._require_configured()
        r = requests.post(
            f"{self.supabase_url}/auth/v1/recover",
            headers=self._headers(),
            json={"email": email.strip()},
            timeout=20,
        )
        if not r.ok:
            raise AuthError(self._error_text(r))

    def refresh_entitlement(self) -> dict[str, Any]:
        if not self.session or not self.api_url:
            return {}
        r = requests.get(
            f"{self.api_url}/entitlement",
            headers=self._headers(self.session.access_token),
            timeout=15,
        )
        if not r.ok:
            raise AuthError(self._error_text(r))
        data = r.json()
        self.session.plan = data.get("plan", self.session.plan)
        self.session.expires_at = data.get("expires_at", self.session.expires_at)
        self.session.dataset_limit = int(data.get("dataset_limit", self.session.dataset_limit))
        self.session.datasets_used = int(data.get("datasets_used", self.session.datasets_used))
        self.session.founder_customer_number = data.get("founder_customer_number")
        return data

    def register_dataset(self, path: str) -> dict[str, Any]:
        """Register one locally analyzed dataset without uploading its contents."""
        if not self.session:
            raise AuthError("Please sign in first.")
        if not self.api_url:
            raise AuthError("License service is not configured yet.")
        p = Path(path)
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        payload = {"dataset_hash": digest, "name": p.name, "size_bytes": p.stat().st_size}
        r = requests.post(
            f"{self.api_url}/datasets/register",
            headers=self._headers(self.session.access_token),
            json=payload,
            timeout=20,
        )
        if not r.ok:
            raise AuthError(self._error_text(r))
        data = r.json()
        self.session.datasets_used = int(data.get("datasets_used", self.session.datasets_used))
        self.session.dataset_limit = int(data.get("dataset_limit", self.session.dataset_limit))
        return data

    def create_checkout(self, plan: str) -> str:
        if not self.session or not self.api_url:
            raise AuthError("Payment service is not configured yet.")
        r = requests.post(
            f"{self.api_url}/billing/checkout",
            headers=self._headers(self.session.access_token),
            json={"plan": plan},
            timeout=20,
        )
        if not r.ok:
            raise AuthError(self._error_text(r))
        url = r.json().get("checkout_url")
        if not url:
            raise AuthError("The billing service did not return a checkout URL.")
        return url

    def logout(self) -> None:
        if self.session and self.configured:
            try:
                requests.post(
                    f"{self.supabase_url}/auth/v1/logout",
                    headers=self._headers(self.session.access_token),
                    timeout=10,
                )
            except Exception:
                pass
        self.session = None

    def _set_session(self, data: dict[str, Any]) -> None:
        user = data.get("user") or {}
        self.session = AuthSession(
            access_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token", ""),
            user_id=user.get("id", ""),
            email=user.get("email", ""),
        )

    def _require_configured(self) -> None:
        if not self.configured:
            raise AuthError(
                "INSITEVA account service is not configured.\n\n"
                "Set INSITEVA_SUPABASE_URL and INSITEVA_SUPABASE_ANON_KEY before release."
            )

    @staticmethod
    def _error_text(response: requests.Response) -> str:
        try:
            data = response.json()
            return data.get("msg") or data.get("message") or data.get("error_description") or str(data)
        except Exception:
            return response.text or f"HTTP {response.status_code}"
