from __future__ import annotations

from fastapi import FastAPI

import atlaspipe
from atlaspipe.api.app import create_app


def test_package_imports() -> None:
    assert atlaspipe.__version__ == "0.1.0"


def test_create_app() -> None:
    app = create_app()
    assert isinstance(app, FastAPI)
    assert app.title == "AtlasPipe"
