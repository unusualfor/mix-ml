from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.client import ping_backend

router = APIRouter()


@router.get("/healthz")
def healthz():
    return {"status": "ok"}


@router.get("/readyz")
def readyz():
    if ping_backend():
        return {"status": "ok"}
    return JSONResponse({"status": "backend_unavailable"}, status_code=503)
