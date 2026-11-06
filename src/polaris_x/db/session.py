from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from polaris_x.db.config import database_url

def make_engine(url: str | None = None):
    return create_engine(url or database_url(), pool_pre_ping=True)

def make_session_factory(url: str | None = None):
    return sessionmaker(bind=make_engine(url), expire_on_commit=False)
