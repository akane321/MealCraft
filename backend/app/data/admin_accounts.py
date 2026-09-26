"""Create or update the fixed operations-console accounts listed in ADMIN_ACCOUNTS (ADR-0047 section 1).

Every listed account gets the same, highest system role; there are no differences between them.
Run at start-up after migrations: ``python -m app.data.admin_accounts``. Idempotent.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.auth.authorization import SystemRole
from app.auth.passwords import Argon2PasswordAdapter
from app.models.platform import UserCredential
from app.repositories.platform import PlatformRepository
from app.schemas.platform import normalize_email


@dataclass(frozen=True)
class AdminAccount:
    email: str
    password: str
    display_name: str


def parse_admin_accounts(value: str) -> list[AdminAccount]:
    """``email:password:Display Name;...``. The name may be left out; a password may not contain ':'."""

    accounts = []
    for entry in filter(None, (part.strip() for part in value.split(";"))):
        email, _, rest = entry.partition(":")
        password, _, display_name = rest.partition(":")
        if not email.strip() or not password:
            raise ValueError("Each ADMIN_ACCOUNTS entry needs at least email:password")
        accounts.append(
            AdminAccount(
                email=normalize_email(email),
                password=password,
                display_name=(display_name.strip() or email.strip())[:120],
            )
        )
    return accounts


def ensure_admin_accounts(session: Session, accounts: list[AdminAccount], passwords: Argon2PasswordAdapter) -> int:
    repository = PlatformRepository(session)
    for account in accounts:
        user = repository.get_user_by_email(account.email)
        if user is None:
            user = repository.create_account(
                normalized_email=account.email,
                display_name=account.display_name,
                password_hash=passwords.hash_password(account.password),
            )
        elif user.credential is None:
            session.add(UserCredential(user_id=user.id, password_hash=passwords.hash_password(account.password)))
        elif not passwords.verify_password(user.credential.password_hash, account.password).valid:
            # The environment is the source of truth for these accounts, so a changed password takes effect.
            user.credential.password_hash = passwords.hash_password(account.password)
        if user.credential is not None:
            user.credential.failed_login_count = 0
            user.credential.locked_until = None
        user.display_name = account.display_name
        user.system_role = SystemRole.ADMIN.value
        user.status = "active"
        session.commit()
    return len(accounts)


def main() -> None:
    from app.core.config import get_settings
    from app.db.session import SessionLocal

    accounts = parse_admin_accounts(get_settings().admin_accounts)
    with SessionLocal() as session:
        count = ensure_admin_accounts(session, accounts, Argon2PasswordAdapter())
    print(f"Admin accounts ensured: {count}")


if __name__ == "__main__":
    main()
