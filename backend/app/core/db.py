# pyrefly: ignore [missing-import]
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
# pyrefly: ignore [missing-import]

from typing import Generator
from app.core.config import settings

import os
engine = create_engine(os.getenv('TEST_DATABASE_URL', settings.DATABASE_URL))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
