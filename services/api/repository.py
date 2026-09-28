import aiosqlite

from . import models


class ImageException(Exception):
    ...


class ImageNotFound(ImageException):
    ...


class ImageRepository:
    def __init__(self, connect: aiosqlite.Connection):
        self._connect = connect

    async def create(self, url: str, width: int, height: int) -> int:
        row_id = await self._connect.execute_insert(
            'INSERT INTO images(image_url, width, height) VALUES (?, ?, ?)',
            (url, width, height)
        )
        await self._connect.commit()
        return row_id[0]

    async def get(self, id: int) -> models.Image:
        async with self._connect.execute(
            'SELECT id, image_url, width, height FROM images WHERE id = ?',
            (id,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                raise ImageNotFound

            return models.Image(id=row[0], url=row[1], width=row[2], height=row[3])

    async def list(self, page: int, count: int) -> list[models.Image]:
        async with self._connect.execute(
            'SELECT id, image_url, width, height FROM images LIMIT ? OFFSET ?',
            (count, (page - 1) * count)
        ) as cur:
            return [
                models.Image(id=row[0], url=row[1], width=row[2], height=row[3])
                for row in await cur.fetchall()
            ]
