"""Central API — FastAPI application entrypoint on :8000."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fmp.api.v1 import dispensing, realtime, tanks
from fmp.core.config import get_settings

logging.basicConfig(level=logging.INFO)
settings = get_settings()

app = FastAPI(
    title="Cloud Fuel & Dispensing Platform API",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dispensing.router)
app.include_router(tanks.router)
app.include_router(realtime.router)


@app.get("/api/v1/health", tags=["system"])
async def health() -> dict:
    return {"status": "ok", "service": "api"}