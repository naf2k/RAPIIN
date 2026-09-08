"""Development entrypoint: python run.py"""
import uvicorn

from beresin.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "beresin.main:app",
        host=settings.beresin_host,
        port=settings.beresin_port,
        reload=False,
    )
