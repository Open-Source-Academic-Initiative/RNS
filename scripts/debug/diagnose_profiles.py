"""Compara el universo de resultados de los dos perfiles bajo los mismos filtros.

Reproduce los parámetros del usuario: 60M..260M, 30 días, todos abiertos,
todas las etapas, sin keyword. Muestra cuántas oportunidades quedan tras
aplicar la lógica de scope de cada perfil.
"""

from __future__ import annotations

import asyncio

from src.infrastructure.repositories import SocrataTenderRepository


async def main() -> None:
    repo = SocrataTenderRepository(snapshot_db_path=":memory:")
    try:
        for profile_name in ("generic_it", "opensai"):
            results = await repo.search_by_criteria(
                min_budget=60_000_000,
                max_budget=260_000_000,
                published_since_days=30,
                profile=profile_name,
            )
            print(f"\n=== Perfil: {profile_name} ===")
            print(f"Total oportunidades: {len(results)}")
            print(f"Top 8 ejemplos:")
            for tender in results[:8]:
                print(
                    f"  · score={tender.match_score:>5.1f} | {tender.match_label:14} | "
                    f"${int(tender.base_price):>13,} | {tender.entity[:32]:32} | "
                    f"{tender.name[:70]}"
                )
            if results:
                opensai_only = [t for t in results if "campus virtual" in t.name.lower() or "moodle" in t.name.lower()]
                print(f"  (matches LMS-like en este perfil: {len(opensai_only)})")
    finally:
        await repo.aclose()


if __name__ == "__main__":
    asyncio.run(main())
