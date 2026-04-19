from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.config import settings
from api.db import get_client, get_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = get_client()
    app.state.db = get_db(client)
    yield
    client.close()


app = FastAPI(title="Shiftwise API", debug=settings.debug, lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}
