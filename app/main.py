import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from .db import engine
from .db import Base
from .routes import auth_router, dashboard_router, provider_router, contract_router, settings_router

BASE_DIR = Path(__file__).resolve().parent

def create_app() -> FastAPI:
    app = FastAPI(title="SmartContract Manager")
    app.add_middleware(
        SessionMiddleware,
        secret_key=os.environ.get("SESSION_SECRET", "supersecretlocal"),
        session_cookie="smartcontract_session",
    )
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    app.include_router(auth_router)
    app.include_router(dashboard_router)
    app.include_router(provider_router)
    app.include_router(contract_router)
    app.include_router(settings_router)
    return app

app = create_app()


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    uploads = BASE_DIR / "static" / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)


@app.get("/healthz")
def healthz(request: Request):
    return {"status": "ok"}
