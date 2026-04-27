from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
import psycopg2
from database import db

router = APIRouter()

TABLAS_PERMITIDAS = [
    "maquinas",
    "procesos",
    "actividades",
    "operarios",
    "users",
    "ordenes",
    "orden_actividades",
    "registros_produccion",
    "estandares_actividad",
]

TABLAS_OCULTAS = ["bonos"]


@router.get("/config/tablas")
def ver_tablas():
    conn = db()
    c = conn.cursor()
    c.execute("""
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'public'
    AND table_type = 'BASE TABLE'
    """)
    tablas = c.fetchall()
    conn.close()
    return tablas


@router.get("/config/tablas_lista")
def tablas_lista():
    conn = db()
    c = conn.cursor()
    c.execute("""
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'public'
    AND table_type = 'BASE TABLE'
    """)
    tablas = [t[0] for t in c.fetchall()]
    conn.close()
    return [t for t in tablas if t not in TABLAS_OCULTAS]


@router.get("/config/maquinas")
def ver_maquinas():
    conn = db()
    c = conn.cursor()
    c.execute("SELECT * FROM maquinas")
    datos = c.fetchall()
    conn.close()
    return datos


@router.post("/config/maquinas")
def crear_maquina(nombre: str):
    conn = db()
    c = conn.cursor()
    c.execute("INSERT INTO maquinas (nombre) VALUES (%s)", (nombre,))
    conn.commit()
    conn.close()
    return {"mensaje": "maquina creada"}


@router.put("/config/maquinas/{id}")
def editar_maquina(id: int, nombre: str):
    conn = db()
    c = conn.cursor()
    c.execute("UPDATE maquinas SET nombre=%s WHERE id=%s", (nombre, id))
    conn.commit()
    conn.close()
    return {"mensaje": "maquina actualizada"}


@router.delete("/config/maquinas/{id}")
def eliminar_maquina(id: int):
    conn = db()
    c = conn.cursor()
    c.execute("DELETE FROM maquinas WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return {"mensaje": "maquina eliminada"}


@router.get("/config/operarios")
def ver_operarios():
    conn = db()
    c = conn.cursor()
    c.execute("SELECT * FROM operarios")
    datos = c.fetchall()
    conn.close()
    return datos


@router.post("/config/operarios")
def crear_operario(nombre: str):
    conn = db()
    c = conn.cursor()
    c.execute("INSERT INTO operarios (nombre) VALUES (%s)", (nombre,))
    conn.commit()
    conn.close()
    return {"mensaje": "operario creado"}


@router.delete("/config/operarios/{id}")
def eliminar_operario(id: int):
    conn = db()
    c = conn.cursor()
    c.execute("DELETE FROM operarios WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return {"mensaje": "operario eliminado"}


@router.put("/config/operarios/{id}")
def editar_operario(id: int, nombre: str):
    conn = db()
    c = conn.cursor()
    c.execute("UPDATE operarios SET nombre=%s WHERE id=%s", (nombre, id))
    conn.commit()
    conn.close()
    return {"mensaje": "operario actualizado"}


@router.get("/config/actividades")
def ver_actividades():
    conn = db()
    c = conn.cursor()
    c.execute("SELECT * FROM actividades")
    datos = c.fetchall()
    conn.close()
    return datos


@router.post("/config/actividades")
def crear_actividad(nombre: str):
    conn = db()
    c = conn.cursor()
    c.execute("INSERT INTO actividades (nombre) VALUES (%s)", (nombre,))
    conn.commit()
    conn.close()
    return {"mensaje": "actividad creada"}


@router.delete("/config/actividades/{id}")
def eliminar_actividad(id: int):
    conn = db()
    c = conn.cursor()
    c.execute("DELETE FROM actividades WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return {"mensaje": "actividad eliminada"}


@router.get("/config/tabla/{tabla}")
def ver_tabla(tabla: str):
    if tabla not in TABLAS_PERMITIDAS:
        return {"error": "tabla no permitida"}
    conn = db()
    c = conn.cursor()
    c.execute(f"SELECT * FROM {tabla}")
    datos = c.fetchall()
    columnas = [col[0] for col in c.description]
    conn.close()
    return {"columnas": columnas, "datos": datos}


@router.post("/config/tabla/{tabla}")
def insertar_fila(tabla: str, datos: list):
    conn = db()
    c = conn.cursor()
    placeholders = ",".join(["%s"] * len(datos))
    query = f"INSERT INTO {tabla} VALUES (DEFAULT,{placeholders})"
    c.execute(query, datos)
    conn.commit()
    conn.close()
    return {"mensaje": "fila creada"}


@router.delete("/config/tabla/{tabla}/{id}")
def eliminar_fila(tabla: str, id: int):
    conn = db()
    c = conn.cursor()
    c.execute(f"DELETE FROM {tabla} WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return {"mensaje": "fila eliminada"}


@router.post("/config/tabla/{tabla}/actualizar")
def actualizar_tabla(tabla: str, data: dict):
    columnas = data["columnas"]
    filas = data["filas"]
    conn = db()
    c = conn.cursor()
    c.execute(f"DELETE FROM {tabla}")
    for fila in filas:
        placeholders = ",".join(["%s"] * len(fila))
        query = f"INSERT INTO {tabla} ({','.join(columnas)}) VALUES ({placeholders})"
        c.execute(query, fila)
    conn.commit()
    conn.close()
    return {"ok": True}


@router.post("/config/tabla/{tabla}/guardar")
def guardar_tabla(tabla: str, data: dict):
    columnas = data["columnas"]
    filas = data["filas"]
    conn = db()
    c = conn.cursor()
    c.execute(f"DELETE FROM {tabla}")
    columnas_insert = columnas[1:]  # ignorar id
    for fila in filas:
        valores = fila[1:]
        placeholders = ",".join(["%s"] * len(valores))
        query = f"INSERT INTO {tabla} ({','.join(columnas_insert)}) VALUES ({placeholders})"
        c.execute(query, valores)
    conn.commit()
    conn.close()
    return {"ok": True}


@router.get("/configuracion", response_class=HTMLResponse)
def configuracion(request: Request):
    if "username" not in request.session:
        return RedirectResponse("/admin?next=configuracion", 303)
    if request.session.get("role") != "admin":
        return RedirectResponse("/", 303)
    return request.app.state.templates.TemplateResponse(
        "configuracion.html",
        {"request": request}
    )
