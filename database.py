import sqlite3

def db():
    return sqlite3.connect("produccion.db")