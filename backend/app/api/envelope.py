"""One response shape for success and errors (section 8.2)."""

import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core import clock
from app.core.resilience import UpstreamError

_CODES = {404: "NOT_FOUND", 422: "VALIDATION_ERROR", 429: "RATE_LIMITED", 502: "UPSTREAM_UNAVAILABLE"}


def new_request_id() -> str:
    return f"req_{uuid.uuid4().hex[:12]}"


def meta(request_id: str, **extra: Any) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "generated_at": clock.now().isoformat(),
        "degraded": False,
        "warnings": [],
        "sources": [],
        **extra,
    }


def error_response(
    status: int, code: str, title: str, detail: str, request_id: str, fields: list[dict] | None = None
) -> JSONResponse:
    body = {
        "ok": False,
        "error": {
            "type": f"urn:leaveby:problem:{title.lower().replace(' ', '-')}",
            "title": title,
            "status": status,
            "code": code,
            "detail": detail,
            "fields": fields or [],
        },
        "meta": meta(request_id),
    }
    return JSONResponse(status_code=status, content=body)


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", None) or new_request_id()


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request.state.request_id = new_request_id()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        fields = [
            {
                "path": ".".join(str(p) for p in e["loc"] if p != "body"),
                "message": str(e["msg"]).removeprefix("Value error, "),
            }
            for e in exc.errors()
        ]
        detail = fields[0]["message"] if fields else "Request validation failed"
        return error_response(
            422, "VALIDATION_ERROR", "Request validation failed", detail.capitalize(), _rid(request), fields
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        code = _CODES.get(exc.status_code, "INTERNAL")
        return error_response(exc.status_code, code, "Request failed", str(exc.detail), _rid(request))

    @app.exception_handler(UpstreamError)
    async def _upstream(request: Request, exc: UpstreamError):
        return error_response(
            502,
            "UPSTREAM_UNAVAILABLE",
            "Upstream unavailable",
            "Can't compute a reliable recommendation right now. Try again in a minute.",
            _rid(request),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        # No stack trace to the client; the request_id ties it to the logs.
        return error_response(500, "INTERNAL", "Internal error", "Something went wrong.", _rid(request))
