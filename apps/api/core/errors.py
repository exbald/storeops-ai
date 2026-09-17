from uuid import UUID, uuid4

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from storeops_contracts.models import Detail, Error

from apps.api.ports.identity import AuthError
from apps.api.ports.state import VersionConflictError


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[Detail] | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []


def build_error_response(
    status_code: int,
    code: str,
    message: str,
    details: list[Detail] | None = None,
    request_id: UUID | None = None,
) -> JSONResponse:
    err = Error(
        code=code[:80],
        message=message[:1000],
        request_id=request_id or uuid4(),
        details=details or [],
    )
    return JSONResponse(status_code=status_code, content=err.model_dump(mode="json"))


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    req_id = getattr(request.state, "request_id", None)
    return build_error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
        request_id=req_id,
    )


async def version_conflict_handler(request: Request, exc: VersionConflictError) -> JSONResponse:
    req_id = getattr(request.state, "request_id", None)
    return build_error_response(
        status_code=status.HTTP_409_CONFLICT,
        code=exc.code,
        message=exc.message,
        request_id=req_id,
    )


async def auth_error_handler(request: Request, exc: AuthError) -> JSONResponse:
    req_id = getattr(request.state, "request_id", None)
    return build_error_response(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code=exc.code,
        message=exc.message,
        request_id=req_id,
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    req_id = getattr(request.state, "request_id", None)
    details: list[Detail] = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err["loc"] if x != "body")
        details.append(Detail(field=loc or None, message=err["msg"]))
    return build_error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="VALIDATION_ERROR",
        message="Request payload failed schema validation",
        details=details,
        request_id=req_id,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    req_id = getattr(request.state, "request_id", None)
    code_map = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "UNPROCESSABLE_ENTITY",
        500: "INTERNAL_ERROR",
    }
    return build_error_response(
        status_code=exc.status_code,
        code=code_map.get(exc.status_code, "HTTP_ERROR"),
        message=str(exc.detail),
        request_id=req_id,
    )
