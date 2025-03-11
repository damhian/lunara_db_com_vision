from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# Import configuration
from app.config import Config

# SQLAlchemy Base and Engine
Base = declarative_base()
engine = create_engine(
    Config.SQLALCHEMY_DATABASE_URI, 
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=3600,
    echo=False
)

# Session Factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Dependency: Get a new database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
