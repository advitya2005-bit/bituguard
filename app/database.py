from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import pathlib

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
DB_FILE = BASE_DIR / "bituguard.db"

engine = create_engine(
    f"sqlite:///{DB_FILE}",
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()
