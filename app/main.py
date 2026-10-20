from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.session import engine
from app.services.quality_checks import recover_interrupted

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    tables = [table for table in Base.metadata.sorted_tables
              if settings.environment == "local" or table.name != "quality_check_runs"]
    Base.metadata.create_all(bind=engine, tables=tables)
    if settings.environment == "local" and settings.quality_runner_enabled:
        recover_interrupted()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Quality-Local"],
)
app.include_router(api_router, prefix=settings.api_prefix)
