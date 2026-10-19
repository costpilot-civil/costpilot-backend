from psycopg_pool import ConnectionPool

from app.infrastructure.config import Settings


def create_db_pool(settings: Settings) -> ConnectionPool:
    return ConnectionPool(
        conninfo="",
        kwargs={
            "dbname": settings.postgres_db,
            "user": settings.postgres_user,
            "password": settings.postgres_password,
            "host": settings.postgres_host,
            "port": settings.postgres_port,
        },
        min_size=1,
        max_size=5,
        open=False,
    )
