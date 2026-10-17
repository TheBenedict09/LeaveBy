import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import envelope
from app.api.routes import router
from app.api.services import Services
from app.core.env import load_env


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await app.state.services.client.aclose()


def create_app(services: Services | None = None) -> FastAPI:
    app = FastAPI(title="LeaveBy API", version="0.1.0", lifespan=lifespan)
    app.state.services = services or Services.create()
    origins = os.environ.get("LEAVEBY_CORS_ORIGINS", "http://localhost:5173").split(",")
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["*"])
    envelope.install(app)
    app.include_router(router)
    return app


logging.getLogger("httpx").setLevel(logging.WARNING)  # request logs would include provider keys
load_env()
app = create_app()
