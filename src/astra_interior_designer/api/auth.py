"""Add authentication endpoints to this router."""

from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])
