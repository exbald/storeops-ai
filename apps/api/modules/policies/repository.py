import asyncio
from typing import Protocol
from uuid import UUID

from storeops_contracts.models import PolicyVersion, Promotion


class PolicyRepository(Protocol):
    async def create_promotion(self, promotion: Promotion) -> Promotion: ...

    async def get_promotion(
        self, workspace_id: UUID, promotion_id: UUID
    ) -> Promotion | None: ...

    async def update_promotion(self, promotion: Promotion) -> Promotion: ...

    async def list_promotions(
        self,
        workspace_id: UUID,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[Promotion], str | None]: ...

    async def create_policy_version(
        self, workspace_id: UUID, policy_version: PolicyVersion
    ) -> PolicyVersion: ...

    async def get_policy_version(
        self, workspace_id: UUID, promotion_id: UUID, version: int
    ) -> PolicyVersion | None: ...

    async def get_policy_version_by_id(
        self, workspace_id: UUID, version_id: UUID
    ) -> PolicyVersion | None: ...

    async def list_policy_versions(
        self,
        workspace_id: UUID,
        promotion_id: UUID,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[PolicyVersion], str | None]: ...


class InMemoryPolicyRepository(PolicyRepository):
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.promotions: dict[tuple[UUID, UUID], Promotion] = {}
        self.policy_versions: dict[tuple[UUID, UUID, int], PolicyVersion] = {}
        self.policy_versions_by_id: dict[tuple[UUID, UUID], PolicyVersion] = {}

    async def create_promotion(
        self, workspace_id: UUID, promotion: Promotion
    ) -> Promotion:
        async with self._lock:
            self.promotions[(workspace_id, promotion.id)] = promotion
            return promotion

    async def get_promotion(
        self, workspace_id: UUID, promotion_id: UUID
    ) -> Promotion | None:
        async with self._lock:
            return self.promotions.get((workspace_id, promotion_id))

    async def update_promotion(
        self, workspace_id: UUID, promotion: Promotion
    ) -> Promotion:
        async with self._lock:
            self.promotions[(workspace_id, promotion.id)] = promotion
            return promotion

    async def list_promotions(
        self,
        workspace_id: UUID,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[Promotion], str | None]:
        async with self._lock:
            promos = [
                p for (ws_id, _), p in self.promotions.items() if ws_id == workspace_id
            ]
            # sort by created_at desc then id tiebreak
            promos.sort(key=lambda p: (p.created_at, p.id), reverse=True)

            start_idx = 0
            if cursor:
                for idx, p in enumerate(promos):
                    if str(p.id) == cursor:
                        start_idx = idx + 1
                        break

            sliced = promos[start_idx : start_idx + limit]
            next_cursor = None
            if start_idx + limit < len(promos) and sliced:
                next_cursor = str(sliced[-1].id)

            return sliced, next_cursor

    async def create_policy_version(
        self, workspace_id: UUID, policy_version: PolicyVersion
    ) -> PolicyVersion:
        async with self._lock:
            key = (workspace_id, policy_version.promotion_id, policy_version.version)
            self.policy_versions[key] = policy_version
            self.policy_versions_by_id[(workspace_id, policy_version.id)] = (
                policy_version
            )
            return policy_version

    async def get_policy_version(
        self, workspace_id: UUID, promotion_id: UUID, version: int
    ) -> PolicyVersion | None:
        async with self._lock:
            return self.policy_versions.get((workspace_id, promotion_id, version))

    async def get_policy_version_by_id(
        self, workspace_id: UUID, version_id: UUID
    ) -> PolicyVersion | None:
        async with self._lock:
            return self.policy_versions_by_id.get((workspace_id, version_id))

    async def list_policy_versions(
        self,
        workspace_id: UUID,
        promotion_id: UUID,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[PolicyVersion], str | None]:
        async with self._lock:
            versions = [
                v
                for (ws_id, pid, _), v in self.policy_versions.items()
                if ws_id == workspace_id and pid == promotion_id
            ]
            versions.sort(key=lambda v: v.version, reverse=True)

            start_idx = 0
            if cursor:
                try:
                    target_ver = int(cursor)
                    for idx, v in enumerate(versions):
                        if v.version == target_ver:
                            start_idx = idx + 1
                            break
                except ValueError:
                    pass

            sliced = versions[start_idx : start_idx + limit]
            next_cursor = None
            if start_idx + limit < len(versions) and sliced:
                next_cursor = str(sliced[-1].version)

            return sliced, next_cursor
