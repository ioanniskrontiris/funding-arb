from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

DB_URL = os.getenv("DB_URL", "sqlite:///./funding_arb.db")

# echo=False = no SQL spam; future=True = 2.0-style engine
engine = create_engine(DB_URL, echo=False, future=True)

# Session factory your code imports as SessionLocal
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)

# Declarative base for ORM models
Base = declarative_base()