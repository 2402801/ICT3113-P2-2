import os
import time

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, func
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import OperationalError

MYSQL_HOST = os.getenv("MYSQL_HOST", "mysql")
MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")
MYSQL_USER = os.getenv("MYSQL_USER", "triage")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "triage")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "triage")

DATABASE_URL = (
    f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
    f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    narrative = Column(Text, nullable=False)
    category = Column(String(64), nullable=False, index=True)
    classification_latency_ms = Column(Float, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class RequestMetric(Base):
    __tablename__ = "request_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    endpoint = Column(String(64), nullable=False, index=True)
    status_code = Column(Integer, nullable=False)
    latency_ms = Column(Float, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


def init_db(retries: int = 30, delay_seconds: float = 2.0) -> None:
    """Create tables, retrying while MySQL is still starting up in Docker Compose."""
    last_error = None
    for _ in range(retries):
        try:
            Base.metadata.create_all(bind=engine)
            return
        except OperationalError as exc:
            last_error = exc
            time.sleep(delay_seconds)
    raise RuntimeError(f"Could not connect to MySQL after {retries} retries") from last_error


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
