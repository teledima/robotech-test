from contextlib import asynccontextmanager
from typing import Annotated

import aiosqlite
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from . import schemas
from .repository import ImageNotFound, ImageRepository


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.connection = await aiosqlite.connect('data/sqlite/excercise.db')
    yield
    await app.state.connection.close()


def get_repo(request: Request):
    return ImageRepository(request.app.state.connection)


app = FastAPI(lifespan=lifespan)
ImageRepoDep = Annotated[ImageRepository, Depends(get_repo)]


@app.post('/images/')
async def upload_image(repo: ImageRepoDep, request: schemas.CreateImage):
    return await repo.create(request.url, request.width, request.height)


@app.get('/images/{id}')
async def get(repo: ImageRepoDep, id: int):
    try:
        return await repo.get(id)
    except ImageNotFound:
        return JSONResponse(content='image not found', status_code=404)


@app.get('/images/')
async def list(repo: ImageRepoDep, page: int = 1, count: int = 10):
    return await repo.list(page, count)
