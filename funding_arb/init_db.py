from .db import engine, Base
from . import models  # noqa: F401 (import side-effect registers models with Base)

def init_db():
    Base.metadata.create_all(bind=engine)