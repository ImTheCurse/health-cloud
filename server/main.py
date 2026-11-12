"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.api import auth, data, health, webhooks
from server.config.logging import configure_logging
from server.config.settings import get_settings
from server.db.session import create_all
from server.observability.middleware import log_requests
from server.providers import get_publisher

# Before the app exists, so anything logged during import or startup lands in
# the configured sink rather than loguru's default one.
configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_all()
    # One connection for the life of the process, on the loop uvicorn is already
    # running -- the lifespan is async, so the client needs no bridging. Started
    # here so an unreachable broker fails the boot loudly instead of surfacing as
    # a 503 on the first real delivery.
    publisher = get_publisher()
    await publisher.start()
    try:
        yield
    finally:
        await publisher.stop()


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
# Registered last, so it is the outermost middleware: it sees the status CORS
# or an error handler finally produced, and still emits a line when something
# below it raises.
app.middleware("http")(log_requests)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(webhooks.router)
app.include_router(data.router)
