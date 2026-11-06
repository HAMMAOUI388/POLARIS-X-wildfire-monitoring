import os

def database_url() -> str:
    return os.getenv("DATABASE_URL", "postgresql+psycopg://polaris:change-me@localhost:5432/polaris_x")
