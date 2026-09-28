from pydantic import BaseModel


class CreateImage(BaseModel):
    url: str
    width: int
    height: int
