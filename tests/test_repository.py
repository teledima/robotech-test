import pytest

import services.api.models as models
from services.api.repository import ImageNotFound


async def test_create_image(repo):
    """Тест создания изображения."""
    image_id = await repo.create(
        url="https://example.com/image.png",
        width=800,
        height=600
    )
    
    assert image_id is not None
    assert isinstance(image_id, int)
    assert image_id > 0


async def test_get_image_success(repo):
    """Тест успешного получения изображения по ID."""
    # Создаем изображение
    image_id = await repo.create(
        url="https://example.com/test.png",
        width=1024,
        height=768
    )
    
    # Получаем изображение
    image = await repo.get(image_id)
    
    assert isinstance(image, models.Image)
    assert image.id == image_id
    assert image.url == "https://example.com/test.png"
    assert image.width == 1024
    assert image.height == 768


async def test_get_image_not_found(repo):
    """Тест получения несуществующего изображения."""
    with pytest.raises(ImageNotFound):
        await repo.get(999)


async def test_list_images_empty(repo):
    """Тест получения пустого списка изображений."""
    images = await repo.list(page=1, count=10)
    
    assert isinstance(images, list)
    assert len(images) == 0


async def test_list_images_with_data(repo):
    """Тест получения списка изображений с данными."""
    # Создаем несколько изображений
    await repo.create("https://example.com/1.png", 100, 100)
    await repo.create("https://example.com/2.png", 200, 200)
    await repo.create("https://example.com/3.png", 300, 300)
    
    images = await repo.list(page=1, count=10)
    
    assert len(images) == 3
    assert all(isinstance(img, models.Image) for img in images)


async def test_list_images_pagination(repo):
    """Тест пагинации списка изображений."""
    # Создаем 5 изображений
    for i in range(5):
        await repo.create(f"https://example.com/{i}.png", 100, 100)
    
    # Первая страница (2 элемента)
    page1 = await repo.list(page=1, count=2)
    assert len(page1) == 2
    assert page1[0].id == 1
    assert page1[1].id == 2
    
    # Вторая страница (2 элемента)
    page2 = await repo.list(page=2, count=2)
    assert len(page2) == 2
    assert page2[0].id == 3
    assert page2[1].id == 4
    
    # Третья страница (2 элемента, но остался только 1)
    page3 = await repo.list(page=3, count=2)
    assert len(page3) == 1
    assert page3[0].id == 5


async def test_list_images_page_beyond_data(repo):
    """Тест запроса страницы за пределами данных."""
    await repo.create("https://example.com/1.png", 100, 100)
    
    images = await repo.list(page=10, count=10)
    
    assert len(images) == 0


async def test_create_multiple_images(repo):
    """Тест создания нескольких изображений."""
    id1 = await repo.create("https://example.com/1.png", 100, 100)
    id2 = await repo.create("https://example.com/2.png", 200, 200)
    id3 = await repo.create("https://example.com/3.png", 300, 300)
    
    assert id1 != id2
    assert id2 != id3
    assert id1 < id2 < id3
