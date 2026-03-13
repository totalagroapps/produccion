import sqlite3

conn = sqlite3.connect("produccion.db")
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS maquinas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS procesos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    maquina_id INTEGER,
    nombre TEXT
)
""")

conn.commit()
conn.close()