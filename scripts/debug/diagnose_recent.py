"""Identifica la fecha de publicación más reciente real del dataset SECOP II."""

from __future__ import annotations

import asyncio
import urllib.parse
from datetime import timedelta

import httpx

from src.infrastructure.repositories import SODA_DATE_FORMAT, SocrataTenderRepository

BASE_URL = SocrataTenderRepository.BASE_URL


async def fetch_count(client: httpx.AsyncClient, where: str) -> int:
    params = [("%24select", "count(1) AS total"), ("%24where", where)]
    qs = "&".join(f"{k}={urllib.parse.quote(v)}" for k, v in params)
    resp = await client.get(f"{BASE_URL}?{qs}", headers={"User-Agent": "RNS-diag/1"})
    resp.raise_for_status()
    payload = resp.json()
    return int(payload[0].get("total") or 0) if payload else 0


async def main() -> None:
    repo = SocrataTenderRepository()
    now = repo._now()

    timeout = httpx.Timeout(60.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        # Top 10 fechas reales (no nulas)
        params = [
            ("%24select", "fecha_de_publicacion_del"),
            ("%24where", "fecha_de_publicacion_del IS NOT NULL"),
            ("%24order", "fecha_de_publicacion_del DESC"),
            ("%24limit", "10"),
        ]
        qs = "&".join(f"{k}={urllib.parse.quote(v)}" for k, v in params)
        resp = await client.get(f"{BASE_URL}?{qs}", headers={"User-Agent": "RNS-diag/1"})
        resp.raise_for_status()
        print("Top 10 fechas más recientes (no nulas):")
        for row in resp.json():
            print(f"  · {row.get('fecha_de_publicacion_del')}")

        # Distribución por día en los últimos 30
        print()
        print("Conteos por umbral, sin opening filter:")
        for d in (1, 3, 5, 7, 10, 14, 21, 30, 45, 60, 90):
            cutoff = (now - timedelta(days=d)).strftime(SODA_DATE_FORMAT)
            total = await fetch_count(client, f"fecha_de_publicacion_del >= '{cutoff}'")
            print(f"  últimos {d:>3} días (>= {cutoff[:10]}): {total}")

        print()
        print("Conteos con opening='Abierto' y precio<=10B:")
        for d in (7, 14, 21, 30, 60, 90):
            cutoff = (now - timedelta(days=d)).strftime(SODA_DATE_FORMAT)
            where = (
                f"precio_base >= 0 AND precio_base <= 10000000000 "
                f"AND estado_de_apertura_del_proceso = 'Abierto' "
                f"AND fecha_de_publicacion_del >= '{cutoff}'"
            )
            total = await fetch_count(client, where)
            print(f"  últimos {d:>3} días: {total}")

    await repo.aclose()


if __name__ == "__main__":
    asyncio.run(main())
