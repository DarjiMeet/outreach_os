from pydantic import BaseModel

class CrawlResult(BaseModel):
    text:str
    source_urls:list[str]