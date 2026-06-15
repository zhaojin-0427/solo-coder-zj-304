from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

SQLALCHEMY_DATABASE_URL = "sqlite:///./baby_med.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate_db():
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(risk_alerts)"))
        columns = [row[1] for row in result.fetchall()]
        if "disposition_status" not in columns:
            conn.execute(text("ALTER TABLE risk_alerts ADD COLUMN disposition_status VARCHAR(20) DEFAULT 'PENDING' NOT NULL"))
            conn.commit()
