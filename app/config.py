import os

class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        # "postgresql://postgres:david083284@localhost/db_comvision"
        "postgresql://postgres:postgres@192.168.2.225/db_comvision"
    )
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False  # To suppress warning messages
