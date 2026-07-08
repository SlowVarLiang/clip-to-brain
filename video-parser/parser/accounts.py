"""多租户账户：每客户独立 API Key、限流与月度额度。"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

_PREFIX = "vp_"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    return _PREFIX + secrets.token_urlsafe(32)


@dataclass
class Account:
    id: str
    name: str
    api_key_hash: str
    enabled: bool = True
    rate_limit_per_minute: int = 0
    monthly_quota: int = 0
    usage: dict[str, int] = field(default_factory=dict)
    created_at: str = ""
    note: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> Account:
        return cls(
            id=str(data["id"]),
            name=str(data.get("name", "")),
            api_key_hash=str(data["api_key_hash"]),
            enabled=bool(data.get("enabled", True)),
            rate_limit_per_minute=int(data.get("rate_limit_per_minute") or 0),
            monthly_quota=int(data.get("monthly_quota") or 0),
            usage={str(k): int(v) for k, v in (data.get("usage") or {}).items()},
            created_at=str(data.get("created_at") or ""),
            note=str(data.get("note") or ""),
        )

    def to_dict(self) -> dict:
        return asdict(self)

    def current_usage(self) -> int:
        return int(self.usage.get(_month_key(), 0))

    def quota_remaining(self) -> int | None:
        if self.monthly_quota <= 0:
            return None
        return max(0, self.monthly_quota - self.current_usage())

    def public_info(self) -> dict:
        remaining = self.quota_remaining()
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "monthly_quota": self.monthly_quota or None,
            "usage_this_month": self.current_usage(),
            "quota_remaining": remaining,
            "created_at": self.created_at,
        }


class AccountStore:
    def __init__(self, path: Path | None = None, legacy_api_key: str = "") -> None:
        raw = os.getenv("ACCOUNTS_FILE", "").strip()
        self.path = path or Path(raw or Path(__file__).resolve().parent.parent / "accounts.json")
        self.legacy_api_key = legacy_api_key.strip()
        self._lock = threading.Lock()
        self._mtime = 0.0
        self._accounts: dict[str, Account] = {}

    def reload_if_needed(self) -> None:
        if not self.path.exists():
            self._accounts = {}
            self._mtime = 0.0
            return
        mtime = self.path.stat().st_mtime
        if mtime == self._mtime:
            return
        with self._lock:
            if not self.path.exists():
                self._accounts = {}
                self._mtime = 0.0
                return
            mtime = self.path.stat().st_mtime
            if mtime == self._mtime:
                return
            data = json.loads(self.path.read_text(encoding="utf-8"))
            accounts = {}
            for item in data.get("accounts", []):
                acc = Account.from_dict(item)
                accounts[acc.id] = acc
            self._accounts = accounts
            self._mtime = mtime

    def _save(self) -> None:
        payload = {"accounts": [a.to_dict() for a in self._accounts.values()]}
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)
        self._mtime = self.path.stat().st_mtime

    def has_any_key(self) -> bool:
        self.reload_if_needed()
        return bool(self.legacy_api_key) or bool(self._accounts)

    def authenticate(self, api_key: str | None) -> Account | None:
        if not api_key:
            return None
        if self.legacy_api_key and secrets.compare_digest(api_key, self.legacy_api_key):
            return Account(
                id="legacy",
                name="default",
                api_key_hash="",
                enabled=True,
                rate_limit_per_minute=0,
                monthly_quota=0,
                created_at="",
            )
        self.reload_if_needed()
        key_hash = hash_api_key(api_key)
        for acc in self._accounts.values():
            if secrets.compare_digest(acc.api_key_hash, key_hash):
                return acc
        return None

    def require_account(self, api_key: str | None) -> Account:
        acc = self.authenticate(api_key)
        if not acc:
            raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")
        if not acc.enabled:
            raise HTTPException(status_code=403, detail="账户已禁用")
        return acc

    def check_quota(self, account: Account) -> None:
        if account.monthly_quota <= 0:
            return
        if account.current_usage() >= account.monthly_quota:
            raise HTTPException(status_code=429, detail="本月转写额度已用完")

    def record_transcribe_usage(self, account: Account) -> None:
        if account.id == "legacy":
            return
        with self._lock:
            self.reload_if_needed()
            acc = self._accounts.get(account.id)
            if not acc:
                return
            month = _month_key()
            acc.usage[month] = int(acc.usage.get(month, 0)) + 1
            self._save()

    def add_account(
        self,
        name: str,
        *,
        rate_limit_per_minute: int = 0,
        monthly_quota: int = 0,
        note: str = "",
    ) -> tuple[Account, str]:
        api_key = generate_api_key()
        acc = Account(
            id=f"acct_{secrets.token_hex(6)}",
            name=name,
            api_key_hash=hash_api_key(api_key),
            enabled=True,
            rate_limit_per_minute=rate_limit_per_minute,
            monthly_quota=monthly_quota,
            created_at=_now_iso(),
            note=note,
        )
        with self._lock:
            self.reload_if_needed()
            self._accounts[acc.id] = acc
            self._save()
        return acc, api_key

    def list_accounts(self) -> list[Account]:
        self.reload_if_needed()
        return sorted(self._accounts.values(), key=lambda a: a.created_at)

    def get_account(self, account_id: str) -> Account | None:
        self.reload_if_needed()
        return self._accounts.get(account_id)

    def set_enabled(self, account_id: str, enabled: bool) -> Account:
        with self._lock:
            self.reload_if_needed()
            acc = self._accounts.get(account_id)
            if not acc:
                raise KeyError(account_id)
            acc.enabled = enabled
            self._save()
            return acc

    def rotate_key(self, account_id: str) -> tuple[Account, str]:
        api_key = generate_api_key()
        with self._lock:
            self.reload_if_needed()
            acc = self._accounts.get(account_id)
            if not acc:
                raise KeyError(account_id)
            acc.api_key_hash = hash_api_key(api_key)
            self._save()
            return acc, api_key

    def update_account(
        self,
        account_id: str,
        *,
        name: str | None = None,
        rate_limit_per_minute: int | None = None,
        monthly_quota: int | None = None,
        note: str | None = None,
    ) -> Account:
        with self._lock:
            self.reload_if_needed()
            acc = self._accounts.get(account_id)
            if not acc:
                raise KeyError(account_id)
            if name is not None:
                acc.name = name
            if rate_limit_per_minute is not None:
                acc.rate_limit_per_minute = rate_limit_per_minute
            if monthly_quota is not None:
                acc.monthly_quota = monthly_quota
            if note is not None:
                acc.note = note
            self._save()
            return acc
