from typing import Protocol


class AuthError(Exception):
    def __init__(self, message: str, code: str = "UNAUTHORIZED"):
        super().__init__(message)
        self.message = message
        self.code = code


class IdentityVerifier(Protocol):
    async def verify_token(self, token: str) -> tuple[str, str | None]:
        """Verify bearer token and return (uid, email).

        Raises AuthError on invalid or missing credentials.
        """
        ...
