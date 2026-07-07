import psycopg2
from psycopg2 import pool
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Inicializamos el pool de conexiones (1 a 20 conexiones)
try:
    db_pool = psycopg2.pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=20,
        dsn=DATABASE_URL
    )
except Exception as e:
    print("Error iniciando Connection Pool:", e)
    db_pool = None

from contextvars import ContextVar

_active_connections = ContextVar("active_connections", default=None)

class PooledConnection:
    """Un wrapper que sobreescribe close() para devolver la conexión al pool en lugar de cerrarla"""
    def __init__(self, conn, pool_ref):
        self.conn = conn
        self.pool_ref = pool_ref
        self._closed = False
        
        # Registrar esta conexión si estamos dentro de un request
        active = _active_connections.get()
        if active is not None:
            active.append(self)
        
    def cursor(self, *args, **kwargs):
        return self.conn.cursor(*args, **kwargs)
        
    def commit(self):
        self.conn.commit()
        
    def rollback(self):
        self.conn.rollback()
        
    def close(self):
        if not self._closed:
            self.pool_ref.putconn(self.conn)
            self._closed = True

def db():
    # Si el pool falló al iniciar, usamos el método tradicional como fallback
    if db_pool is None:
        return psycopg2.connect(DATABASE_URL)
        
    conn = db_pool.getconn()
    return PooledConnection(conn, db_pool)
