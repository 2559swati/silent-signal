# pyrefly: ignore [missing-import]
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
# pyrefly: ignore [missing-import]

from typing import Generator
from app.core.config import settings

import os
db_url = os.getenv('TEST_DATABASE_URL', settings.DATABASE_URL)
# SQLite needs check_same_thread=False for FastAPI/uvicorn threads.
connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
engine = create_engine(db_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
