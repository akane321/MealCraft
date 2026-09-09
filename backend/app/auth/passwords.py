from __future__ import annotations

from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type


@dataclass(frozen=True)
class Argon2PasswordPolicy:
    """Versioned application policy for password hashing.

    The values match the argon2-cffi low-memory profile currently selected for
    the web application. Changing any value requires a policy-version bump;
    successful logins then upgrade older hashes opportunistically.
    """

    version: str = "argon2id-v1"
    time_cost: int = 3
    memory_cost_kib: int = 65_536
    parallelism: int = 4
    hash_length: int = 32
    salt_length: int = 16


@dataclass(frozen=True)
class PasswordVerification:
    valid: bool
    upgraded_hash: str | None = None


class Argon2PasswordAdapter:
    """Small, reviewable boundary around the maintained Argon2 implementation."""

    def __init__(self, policy: Argon2PasswordPolicy | None = None) -> None:
        self.policy = policy or Argon2PasswordPolicy()
        self._hasher = PasswordHasher(
            time_cost=self.policy.time_cost,
            memory_cost=self.policy.memory_cost_kib,
            parallelism=self.policy.parallelism,
            hash_len=self.policy.hash_length,
            salt_len=self.policy.salt_length,
            type=Type.ID,
        )
        # A missing account follows the same expensive verification path as a
        # real account. The value is process-local and never persisted.
        self._dummy_hash = self._hasher.hash("mealcraft-dummy-password-verification")

    def hash_password(self, password: str) -> str:
        if not password:
            raise ValueError("password cannot be empty")
        return self._hasher.hash(password)

    def verify_password(self, encoded_hash: str | None, password: str) -> PasswordVerification:
        candidate_hash = encoded_hash or self._dummy_hash
        try:
            valid = self._hasher.verify(candidate_hash, password)
        except (InvalidHashError, VerificationError, VerifyMismatchError):
            return PasswordVerification(valid=False)

        if not valid or encoded_hash is None:
            return PasswordVerification(valid=False)
        if self._hasher.check_needs_rehash(encoded_hash):
            return PasswordVerification(valid=True, upgraded_hash=self._hasher.hash(password))
        return PasswordVerification(valid=True)
