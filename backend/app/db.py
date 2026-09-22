from psycopg import connect

from .config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD


def get_db_connection():
    return connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )