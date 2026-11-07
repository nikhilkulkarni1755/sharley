import os

from fastapi import FastAPI

from sharley.api.app import create_app
from sharley.gate.context import Context


def build_app() -> FastAPI:
    """uvicorn --factory sharley.api:build_app"""
    origins = [o for o in os.environ.get("SHARLEY_CORS_ORIGINS", "http://localhost:3000").split(",") if o]
    return create_app(Context.from_env(os.environ), origins)


__all__ = ["build_app", "create_app"]
