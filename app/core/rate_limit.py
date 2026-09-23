import time
import logging
from typing import Optional, Dict, Union
from uuid import UUID
from fastapi import Request, Depends, HTTPException
from app.core.redis import redis_manager
from app.core.exceptions import APIException
from app.models.user import User, UserRole
from app.dependencies import get_current_active_user

logger = logging.getLogger(__name__)

# Fallback in-memory cache if Redis is temporarily unreachable
_memory_store: Dict[str, tuple[int, float]] = {}


class RateLimiter:
    """
    Reusable Rate Limiter for FastAPI endpoints.
    
    Supports:
    - User-based limits parameterized by UserRole
    - IP-based limits for public/unauthenticated routes
    - Redis-backed storage with automatic expiration
    - Graceful fallback to in-memory store if Redis is unavailable
    - Quota rollback mechanism when downstream operations fail
    
    Usage:
        # 1. As a dependency
        pronunciation_limiter = RateLimiter(
            resource="pronunciation_practice",
            role_limits={
                UserRole.GUEST_STUDENT: 10,
                UserRole.STUDENT: 50,
            },
            default_limit=50,
            period_seconds=86400,
        )
        
        @router.post("/practices", dependencies=[Depends(pronunciation_limiter)])
        async def create_practice(...):
            ...
            
        # 2. In error handling / rollback:
        except Exception:
            await pronunciation_limiter.rollback(current_user.id)
            raise
    """

    def __init__(
        self,
        resource: str,
        role_limits: Optional[Dict[Union[UserRole, str], int]] = None,
        default_limit: int = 50,
        period_seconds: int = 86400,
        by_ip: bool = False,
    ):
        self.resource = resource
        self.role_limits = role_limits or {}
        self.default_limit = default_limit
        self.period_seconds = period_seconds
        self.by_ip = by_ip

    def _get_limit_for_role(self, role: Optional[Union[UserRole, str]]) -> int:
        if role is None:
            return self.default_limit
        role_val = role.value if isinstance(role, UserRole) else str(role)
        for r, limit in self.role_limits.items():
            r_val = r.value if isinstance(r, UserRole) else str(r)
            if r_val == role_val:
                return limit
        return self.default_limit

    def get_cache_key(self, identifier: Union[str, UUID]) -> str:
        prefix = "ip" if self.by_ip else "user"
        return f"ratelimit:{self.resource}:{prefix}:{str(identifier)}"

    async def check_and_consume(
        self, identifier: Union[str, UUID], role: Optional[Union[UserRole, str]] = None
    ) -> dict:
        """
        Check and consume 1 quota unit.
        Raises APIException(429) if quota exceeded.
        Returns dict with usage info: {"used": int, "limit": int, "remaining": int}.
        """
        limit = self._get_limit_for_role(role)
        key = self.get_cache_key(identifier)

        client = redis_manager.redis_client
        if client:
            try:
                current_count = await client.get(key)
                count = int(current_count) if current_count else 0

                if count >= limit:
                    raise APIException(
                        status_code=429,
                        code="RATE_LIMIT_EXCEEDED",
                        message=f"Đã đạt giới hạn {limit} lượt/ngày cho tính năng này. Vui lòng thử lại sau.",
                        details={"limit": limit, "used": count, "remaining": 0},
                    )

                pipe = client.pipeline()
                pipe.incr(key)
                if not current_count:
                    pipe.expire(key, self.period_seconds)
                await pipe.execute()

                return {
                    "key": key,
                    "used": count + 1,
                    "limit": limit,
                    "remaining": max(0, limit - (count + 1)),
                }
            except APIException:
                raise
            except Exception as e:
                logger.warning(f"Redis rate-limit error, falling back to memory: {e}")

        # In-memory fallback
        now = time.time()
        # Clean expired keys
        expired_keys = [k for k, (_, exp) in _memory_store.items() if exp <= now]
        for k in expired_keys:
            _memory_store.pop(k, None)

        count, expire_at = _memory_store.get(key, (0, now + self.period_seconds))
        if count >= limit and expire_at > now:
            raise APIException(
                status_code=429,
                code="RATE_LIMIT_EXCEEDED",
                message=f"Đã đạt giới hạn {limit} lượt/ngày cho tính năng này. Vui lòng thử lại sau.",
                details={"limit": limit, "used": count, "remaining": 0},
            )

        new_count = count + 1
        _memory_store[key] = (new_count, expire_at)
        return {
            "key": key,
            "used": new_count,
            "limit": limit,
            "remaining": max(0, limit - new_count),
        }

    async def rollback(self, identifier: Union[str, UUID]) -> None:
        """Rollback 1 quota unit in case of downstream failures."""
        key = self.get_cache_key(identifier)
        client = redis_manager.redis_client
        if client:
            try:
                await client.decr(key)
                return
            except Exception as e:
                logger.warning(f"Redis rate-limit rollback error: {e}")

        if key in _memory_store:
            count, exp = _memory_store[key]
            if count > 0:
                _memory_store[key] = (count - 1, exp)

    async def get_usage(
        self, identifier: Union[str, UUID], role: Optional[Union[UserRole, str]] = None
    ) -> dict:
        """Inspect current usage without consuming quota."""
        limit = self._get_limit_for_role(role)
        key = self.get_cache_key(identifier)
        client = redis_manager.redis_client
        count = 0
        if client:
            try:
                current_count = await client.get(key)
                if current_count:
                    count = int(current_count)
            except Exception as e:
                logger.warning(f"Redis rate-limit inspect error: {e}")
                if key in _memory_store:
                    count, _ = _memory_store[key]
        elif key in _memory_store:
            count, _ = _memory_store[key]

        return {
            "used": count,
            "limit": limit,
            "remaining": max(0, limit - count),
        }

    async def __call__(
        self,
        request: Request,
        current_user: Optional[User] = Depends(get_current_active_user),
    ) -> dict:
        """FastAPI Dependency callable."""
        if self.by_ip or current_user is None:
            forwarded = request.headers.get("X-Forwarded-For")
            ip = forwarded.split(",")[0].strip() if forwarded else request.client.host
            identifier = ip
            role = None
        else:
            identifier = current_user.id
            role = current_user.role

        quota_info = await self.check_and_consume(identifier=identifier, role=role)
        request.state.rate_limit_info = quota_info
        return quota_info
