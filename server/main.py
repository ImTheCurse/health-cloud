"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.api import auth, health, webhooks
from server.config.logging import configure_logging
from server.config.settings import get_settings
from server.db.session import create_all


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    create_all()
    yield


app = FastAPI(title="health-cloud", lifespan=lifespan)

# The browser must send the session cookie, so credentials are allowed and
# origins are listed explicitly -- a wildcard is rejected in that mode.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(webhooks.router)
