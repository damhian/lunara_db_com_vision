from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# Import configuration
from app.config import Config

# SQLAlchemy Base and Engine
Base = declarative_base()
engine = create_engine(
    Config.SQLALCHEMY_DATABASE_URI, 
    pool_size=5,
    max_overflow=5,
    pool_timeout=10,
    pool_recycle=300,
    echo=False,
    connect_args={
        "connect_timeout": 5,     
        "keepalives": 1,          
        "keepalives_idle": 30,    
        "keepalives_interval": 10, 
        "keepalives_count": 5      
    }
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
