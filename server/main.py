"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from server.api import health
from server.db.session import create_all


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_all()
    yield


app = FastAPI(title="health-cloud", lifespan=lifespan)
app.include_router(health.router)
