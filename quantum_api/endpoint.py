from functools import wraps
from typing import Optional, Callable, List, Type, Any
from pydantic import BaseModel, ValidationError
import time
from .logging import log_request
from .response import APIError
from quantum_encryption import validate_jwt
from multi_factor_auth import require_mfa

class RateLimiter:
    """Token bucket rate limiter for API endpoints"""
    def __init__(self, requests_per_minute: int):
        self.tokens_per_second = requests_per_minute / 60
        self.max_tokens = requests_per_minute
        self.tokens = self.max_tokens
        self.last_update = time.monotonic()

    def acquire(self) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_update
        self.tokens = min(self.tokens + elapsed * self.tokens_per_second, self.max_tokens)
        self.last_update = now
        
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False

def endpoint(
    route: str,
    methods: List[str] = ["GET"],
    *,
    auth_required: bool = False,
    required_roles: List[str] = None,
    rate_limit: int = 100,
    request_schema: Optional[Type[BaseModel]] = None,
    response_schema: Optional[Type[BaseModel]] = None,
    summary: str = None,
    description: str = None
):
    """Production-grade API endpoint decorator with security and validation features"""
    def decorator(func: Callable):
        limiter = RateLimiter(rate_limit)
        
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            request = kwargs.get('request') or (args[0] if args else None)
            
            if not request:
                raise APIError(status_code=500, detail="Request context missing")

            # Rate limiting
            if not limiter.acquire():
                raise APIError(status_code=429, detail="Too many requests")

            # Authentication flow
            user = None
            if auth_required:
                auth_header = request.headers.get("Authorization", "")
                if not auth_header.startswith("Bearer "):
                    raise APIError(status_code=401, detail="Invalid auth scheme")
                
                user = validate_jwt(auth_header[7:])
                if not user or not user.active:
                    raise APIError(status_code=401, detail="Invalid credentials")
                
                if not require_mfa(user):
                    raise APIError(status_code=403, detail="MFA required")

                if required_roles and not set(required_roles).intersection(user.roles):
                    raise APIError(status_code=403, detail="Insufficient permissions")

            # Request validation
            validated_data = None
            if request_schema:
                try:
                    if request.method in ["POST", "PUT", "PATCH"]:
                        validated_data = request_schema(**request.json())
                    else:
                        validated_data = request_schema(**request.query_params)
                    kwargs["validated_data"] = validated_data
                except ValidationError as e:
                    raise APIError(status_code=422, detail=e.errors())

            # Execute endpoint logic
            try:
                response = func(*args, **kwargs)
                
                # Apply response schema validation
                if response_schema and not isinstance(response, response_schema):
                    raise APIError(status_code=500, detail="Response validation failed")
                
                # Log successful request
                log_request(
                    success=True,
                    endpoint=route,
                    method=request.method,
                    status_code=200,
                    user_id=user.id if user else None
                )
                return response
                
            except APIError as e:
                log_request(
                    success=False,
                    endpoint=route,
                    method=request.method,
                    status_code=e.status_code,
                    error=str(e.detail),
                    user_id=user.id if user else None
                )
                raise
            except Exception as e:
                log_request(
                    success=False,
                    endpoint=route,
                    method=request.method,
                    status_code=500,
                    error=str(e),
                    user_id=user.id if user else None
                )
                raise APIError(status_code=500, detail="Internal server error") from e

        # OpenAPI documentation attributes
        wrapper.__doc__ = description or func.__doc__
        wrapper.summary = summary or func.__name__.replace('_', ' ').title()
        wrapper.methods = methods
        wrapper.auth_required = auth_required
        wrapper.rate_limit = rate_limit
        wrapper.request_schema = request_schema
        wrapper.response_schema = response_schema
        
        return wrapper
    return decorator
