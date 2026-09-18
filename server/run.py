"""Development entrypoint: python run.py"""
import uvicorn

from rapiin.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "rapiin.main:app",
        host=settings.rapiin_host,
        port=settings.rapiin_port,
        reload=False,
    )
