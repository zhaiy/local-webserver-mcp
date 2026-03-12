from typing import Any

from pydantic import BaseModel, Field


class HttpResponse(BaseModel):
    status_code: int
    headers: dict[str, str]
    body: str


class SearchResult(BaseModel):
    title: str = ""
    url: str = ""
    snippet: str = ""


class WebLink(BaseModel):
    text: str
    url: str


class WebpageContent(BaseModel):
    url: str
    title: str = ""
    content: str = ""
    headings: list[str] = Field(default_factory=list)
    links: list[WebLink] | None = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    message: str


class SuccessResponse(BaseModel):
    success: bool = True
    data: Any
