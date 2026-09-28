async def test_upload_image(client):
    """Тест загрузки изображения через API."""
    response = await client.post(
        "/images/",
        json={
            "url": "https://example.com/upload.png",
            "width": 1920,
            "height": 1080
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, int)
    assert data > 0


async def test_upload_image_missing_fields(client):
    """Тест загрузки изображения без обязательных полей."""
    response = await client.post(
        "/images/",
        json={
            "url": "https://example.com/image.png"
        }
    )
    
    assert response.status_code == 422


async def test_get_image_by_id(client):
    """Тест получения изображения по ID через API."""
    # Создаем изображение
    create_response = await client.post(
        "/images/",
        json={
            "url": "https://example.com/get-test.png",
            "width": 800,
            "height": 600
        }
    )
    image_id = create_response.json()
    
    # Получаем изображение
    get_response = await client.get(f"/images/{image_id}")
    
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["id"] == image_id
    assert data["url"] == "https://example.com/get-test.png"
    assert data["width"] == 800
    assert data["height"] == 600


async def test_get_image_not_found(client):
    """Тест получения несуществующего изображения через API."""
    response = await client.get("/images/999")
    
    assert response.status_code == 404
    assert response.json() == "image not found"


async def test_list_images_empty(client):
    """Тест получения пустого списка изображений через API."""
    response = await client.get("/images/")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


async def test_list_images_with_data(client):
    """Тест получения списка изображений через API."""
    # Создаем несколько изображений
    await client.post("/images/", json={
        "url": "https://example.com/1.png",
        "width": 100,
        "height": 100
    })
    await client.post("/images/", json={
        "url": "https://example.com/2.png",
        "width": 200,
        "height": 200
    })
    
    response = await client.get("/images/")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["url"] == "https://example.com/1.png"
    assert data[1]["url"] == "https://example.com/2.png"


async def test_list_images_pagination(client):
    """Тест пагинации через API."""
    # Создаем 5 изображений
    for i in range(5):
        await client.post("/images/", json={
            "url": f"https://example.com/{i}.png",
            "width": 100,
            "height": 100
        })
    
    # Запрос с параметрами пагинации
    response = await client.get("/images/?page=2&count=2")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


async def test_list_images_default_pagination(client):
    """Тест пагинации по умолчанию."""
    await client.post("/images/", json={
        "url": "https://example.com/1.png",
        "width": 100,
        "height": 100
    })
    
    # Запрос без параметров (используются значения по умолчанию)
    response = await client.get("/images/")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1


async def test_upload_image_invalid_types(client):
    """Тест загрузки изображения с некорректными типами данных."""
    response = await client.post(
        "/images/",
        json={
            "url": "https://example.com/image.png",
            "width": "not-a-number",
            "height": 600
        }
    )
    
    assert response.status_code == 422


async def test_get_image_negative_id(client):
    """Тест запроса изображения с отрицательным ID."""
    response = await client.get("/images/-1")
    
    assert response.status_code == 404
