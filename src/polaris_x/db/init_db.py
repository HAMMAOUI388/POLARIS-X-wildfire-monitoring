from alembic import command
from alembic.config import Config
from polaris_x.db.config import database_url

def upgrade_database():
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url().replace("%", "%%"))
    command.upgrade(config, "head")

if __name__ == "__main__":
    upgrade_database()
