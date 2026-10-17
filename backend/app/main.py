from fastapi import FastAPI

from app.api import envelope
from app.api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="LeaveBy API", version="0.1.0")
    envelope.install(app)
    app.include_router(router)
    return app


app = create_app()
