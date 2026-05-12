from pathlib import Path

from fastapi.templating import Jinja2Templates

_BASE = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=_BASE / "templates")
