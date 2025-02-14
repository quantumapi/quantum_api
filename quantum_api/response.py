from datetime import datetime
from pydantic import BaseModel
from typing import Any, Optional, Dict
import json
from uuid import uuid4

class APIError(Exception):
    """Standardized error response for API exceptions"""
    def __init__(self, status_code: int, detail: str, error_code: Optional[str] = None):
        self.status_code = status_code
        self.detail = detail
        self.error_code = error_code or f"ERR_{status_code}"
        self.timestamp = datetime.utcnow().isoformat()
        self.error_id = str(uuid4())
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": {
                "id": self.error_id,
                "code": self.error_code,
                "status": self.status_code,
                "detail": self.detail,
                "timestamp": self.timestamp
            }
        }

class BaseResponse(BaseModel):
    """Base response model for all API responses"""
    status: int
    data: Optional[Any] = None
    meta: Optional[Dict[str, Any]] = None
    timestamp: str = datetime.utcnow().isoformat()
    
    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat(),
        }

class ValidationErrorResponse(BaseResponse):
    """Standard response for validation errors"""
    errors: list

def response(
    data: Any = None,
    status: int = 200,
    meta: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Production-grade response handler with:
    - Standardized response format
    - Error handling
    - Metadata support
    - Automatic timestamping
    """
    response_data = BaseResponse(
        status=status,
        data=data,
        meta=meta
    ).dict()
    
    return {
        "content": json.dumps(response_data, default=custom_serializer),
        "status_code": status,
        "headers": headers or {},
        "media_type": "application/json"
    }

def custom_serializer(obj: Any) -> Any:
    """Custom JSON serializer for complex objects"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, uuid4):
        return str(obj)
    raise TypeError(f"Type {type(obj)} not serializable")

def error_response(
    error: APIError,
    headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Standardized error response formatter"""
    error_data = error.to_dict()
    error_data["meta"] = {
        "request_id": str(uuid4()),
        "docs": "https://api.example.com/docs/errors"
    }
    
    return {
        "content": json.dumps(error_data, default=custom_serializer),
        "status_code": error.status_code,
        "headers": headers or {},
        "media_type": "application/json"
    }

# Common error helpers
def bad_request(detail: str = "Invalid request") -> APIError:
    return APIError(400, detail, "BAD_REQUEST")

def unauthorized(detail: str = "Authentication required") -> APIError:
    return APIError(401, detail, "UNAUTHORIZED")

def forbidden(detail: str = "Permission denied") -> APIError:
    return APIError(403, detail, "FORBIDDEN")

def not_found(detail: str = "Resource not found") -> APIError:
    return APIError(404, detail, "NOT_FOUND")

def internal_error(detail: str = "Internal server error") -> APIError:
    return APIError(500, detail, "INTERNAL_ERROR")
