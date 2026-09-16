from typing import Protocol
from uuid import UUID, uuid4


class IdFactory(Protocol):
    def new_id(self) -> UUID:
        """Generate a new unique identifier."""
        ...


class Uuid4Factory:
    def new_id(self) -> UUID:
        return uuid4()
