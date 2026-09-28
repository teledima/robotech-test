import aiosqlite
import pytest
from httpx import ASGITransport, AsyncClient

from services.api.repository import ImageRepository
from services.api.server import app


@pytest.fixture
async def db_connection():
    """In-memory SQLite для тестов."""
    conn = await aiosqlite.connect(":memory:")
    # Создаем таблицу
    await conn.execute("""
        CREATE TABLE images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_url TEXT NOT NULL,
            width INTEGER NOT NULL,
            height INTEGER NOT NULL
        )
    """)
    await conn.commit()
    yield conn
    await conn.close()


@pytest.fixture
async def repo(db_connection):
    """Репозиторий для тестов."""
    return ImageRepository(db_connection)


@pytest.fixture
async def client(db_connection):
    """Async HTTP клиент для тестирования API."""
    # Подменяем соединение в приложении
    app.state.connection = db_connection
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
