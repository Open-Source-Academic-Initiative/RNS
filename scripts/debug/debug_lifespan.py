import asyncio

import _bootstrap  # noqa: F401

from src.presentation.web import app, lifespan

async def main():
    cm = lifespan(app)
    print('before', flush=True)
    await cm.__aenter__()
    print('entered', flush=True)
    await cm.__aexit__(None, None, None)
    print('done', flush=True)

asyncio.run(main())
