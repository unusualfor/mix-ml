import json
import logging
import sys

from fastapi import FastAPI

from app.config import settings
from app.routers import bottles, classes, cocktails, health, recipes


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        obj = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(obj, ensure_ascii=False)


def _setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())


def create_app() -> FastAPI:
    _setup_logging()

    application = FastAPI(title="Mix-ML Cocktail API", version="0.1.0")
    application.include_router(health.router)
    application.include_router(classes.router, prefix="/api")
    application.include_router(recipes.router, prefix="/api")
    application.include_router(bottles.router, prefix="/api")
    application.include_router(cocktails.router, prefix="/api")
    return application


app = create_app()
