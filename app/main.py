import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from .db import engine
from .db import Base
from .i18n import LANGUAGE_NAMES, DEFAULT_LOCALE, get_locale
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


@app.get("/set-language/{locale}")
def set_language(locale: str, request: Request):
    if locale not in LANGUAGE_NAMES:
        locale = DEFAULT_LOCALE
    next_url = request.query_params.get("next", "/")
    if not next_url.startswith("/"):
        next_url = "/"
    response = RedirectResponse(url=next_url, status_code=302)
    response.set_cookie("lang", locale, max_age=31536000, path="/")
    return response


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    uploads = BASE_DIR / "static" / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)


@app.get("/healthz")
def healthz(request: Request):
    return {"status": "ok"}
