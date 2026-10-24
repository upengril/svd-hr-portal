import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from .config import DB_CONFIG

# Connection Pool
db_pool = None

def init_db_pool():
    global db_pool
    if db_pool is None:
        db_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=20,
            **DB_CONFIG
        )

@contextmanager
def get_db():
    global db_pool
    if db_pool is None:
        init_db_pool()
    conn = db_pool.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        db_pool.putconn(conn)

def execute_query(query, params=None, fetch_all=True, fetch_one=False):
    with get_db() as cur:
        cur.execute(query, params or ())
        if fetch_one:
            return cur.fetchone()
        if fetch_all:
            return cur.fetchall()
        return None
