"""Aísla cuál de los filtros base vacía la consulta SECOP."""

from __future__ import annotations

import asyncio
import urllib.parse
from datetime import timedelta

import httpx

import _bootstrap  # noqa: F401

from src.infrastructure.repositories import (
    SODA_DATE_FORMAT,
    SocrataTenderRepository,
)


BASE_URL = SocrataTenderRepository.BASE_URL


async def fetch_count(client: httpx.AsyncClient, where: str) -> int:
    params = [("%24select", "count(1) AS total"), ("%24where", where)]
    qs = "&".join(f"{k}={urllib.parse.quote(v)}" for k, v in params)
    resp = await client.get(f"{BASE_URL}?{qs}", headers={"User-Agent": "RNS-diag/1"})
    resp.raise_for_status()
    payload = resp.json()
    return int(payload[0].get("total") or 0) if payload else 0


async def fetch_distinct(client: httpx.AsyncClient, field: str, where: str = "") -> list[str]:
    params = [
        ("%24select", f"distinct {field}"),
        ("%24limit", "20"),
    ]
    if where:
        params.append(("%24where", where))
    qs = "&".join(f"{k}={urllib.parse.quote(v)}" for k, v in params)
    resp = await client.get(f"{BASE_URL}?{qs}", headers={"User-Agent": "RNS-diag/1"})
    resp.raise_for_status()
    payload = resp.json()
    return [row.get(field) for row in payload if row.get(field) is not None]


async def main() -> None:
    repo = SocrataTenderRepository()
    now = repo._now()
    cutoff_7 = (now - timedelta(days=7)).strftime(SODA_DATE_FORMAT)
    cutoff_30 = (now - timedelta(days=30)).strftime(SODA_DATE_FORMAT)
    cutoff_90 = (now - timedelta(days=90)).strftime(SODA_DATE_FORMAT)

    layers = [
        ("Sin filtros", "1=1"),
        ("opening_status=Abierto", "estado_de_apertura_del_proceso = 'Abierto'"),
        ("publicación 7 días", f"fecha_de_publicacion_del >= '{cutoff_7}'"),
        ("publicación 30 días", f"fecha_de_publicacion_del >= '{cutoff_30}'"),
        ("publicación 90 días", f"fecha_de_publicacion_del >= '{cutoff_90}'"),
        ("precio_base 0..10B", "precio_base >= 0 AND precio_base <= 10000000000"),
        ("precio_base + Abierto", "precio_base >= 0 AND precio_base <= 10000000000 AND estado_de_apertura_del_proceso = 'Abierto'"),
        ("precio_base + Abierto + 90d", f"precio_base >= 0 AND precio_base <= 10000000000 AND estado_de_apertura_del_proceso = 'Abierto' AND fecha_de_publicacion_del >= '{cutoff_90}'"),
        ("precio_base + Abierto + 30d", f"precio_base >= 0 AND precio_base <= 10000000000 AND estado_de_apertura_del_proceso = 'Abierto' AND fecha_de_publicacion_del >= '{cutoff_30}'"),
        ("precio_base + Abierto + 7d", f"precio_base >= 0 AND precio_base <= 10000000000 AND estado_de_apertura_del_proceso = 'Abierto' AND fecha_de_publicacion_del >= '{cutoff_7}'"),
    ]

    timeout = httpx.Timeout(60.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        for label, where in layers:
            try:
                total = await fetch_count(client, where)
            except Exception as exc:
                total = f"ERR {exc!r}"
            print(f"{total!s:>12}  {label}")

        print()
        print("Valores reales de estado_de_apertura_del_proceso (sin filtro):")
        for v in await fetch_distinct(client, "estado_de_apertura_del_proceso"):
            print(f"  · {v!r}")

        print()
        print("Top 5 fechas de publicación más recientes:")
        params = [
            ("%24select", "fecha_de_publicacion_del"),
            ("%24order", "fecha_de_publicacion_del DESC"),
            ("%24limit", "5"),
        ]
        qs = "&".join(f"{k}={urllib.parse.quote(v)}" for k, v in params)
        resp = await client.get(f"{BASE_URL}?{qs}", headers={"User-Agent": "RNS-diag/1"})
        resp.raise_for_status()
        for row in resp.json():
            print(f"  · {row.get('fecha_de_publicacion_del')}")

    await repo.aclose()


if __name__ == "__main__":
    asyncio.run(main())
