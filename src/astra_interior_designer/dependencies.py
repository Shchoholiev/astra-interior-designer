"""Shared FastAPI dependency providers."""

from functools import lru_cache

from astra_interior_designer.config import Settings


@lru_cache
def get_settings() -> Settings:
    return Settings()
