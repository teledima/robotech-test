from pydantic import BaseModel


class Image(BaseModel):
    id: int
    url: str
    width: int
    height: int
