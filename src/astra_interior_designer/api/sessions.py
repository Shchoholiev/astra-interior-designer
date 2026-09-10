"""Add session endpoints to this router."""

from fastapi import APIRouter

router = APIRouter(prefix="/sessions", tags=["sessions"])
