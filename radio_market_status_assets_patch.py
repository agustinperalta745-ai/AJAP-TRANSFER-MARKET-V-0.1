"""Materialize the user-provided transparent market artworks for Radio Pasillo."""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path

import radio_market_status_patch as market_status


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"


def _materialize(stem: str) -> Path:
    encoded = "".join(
        (ASSETS / f"{stem}.b64.{part}").read_text(encoding="ascii").strip()
        for part in (1, 2)
    )
    data = base64.b64decode(encoded, validate=True)
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError(f"Asset inválido: {stem}")
    target = Path(tempfile.gettempdir()) / f"{stem}.png"
    target.write_bytes(data)
    return target


market_status.MARKET_OPEN_IMAGE = _materialize("radio_market_open_ajpa")
market_status.MARKET_CLOSED_IMAGE = _materialize("radio_market_closed_ajpa")

print("AJPA Radio Pasillo: artes transparentes ABIERTO/CERRADO cargados")
