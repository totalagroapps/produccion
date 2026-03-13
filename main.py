from fastapi import FastAPI, Request, Form, UploadFile, File, Depends  # type: ignore
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse  # type: ignore
from fastapi.templating import Jinja2Templates  # type: ignore
from starlette.middleware.sessions import SessionMiddleware  # type: ignore
from datetime import datetime, timedelta
from openpyxl import Workbook  # type: ignore
from fastapi.staticfiles import StaticFiles  # type: ignore
from dotenv import load_dotenv
from auth import login_user, require_admin
from database import db
from fastapi.templating import Jinja2Templates
from routers.ordenes import router as ordenes_router
from routers.usuarios import router as usuarios_router
from routers.android import router as android_router
from routers.inventario import router as inventario_router
from routers.metricas import router as metricas_router
from routers.bonos import router as bonos_router
from routers.admin_tools import router as admin_tools_router
from fastapi import Form
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from routers import configuracion
from routers import admin_panel

templates = Jinja2Templates(directory="templates")

import os
import sqlite3
import pandas as pd  # type: ignore
import random

from dotenv import load_dotenv
import os

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

app.include_router(android_router)

app.include_router(inventario_router)

app.include_router(metricas_router)

app.include_router(bonos_router)

app.include_router(admin_tools_router)

app.include_router(configuracion.router)

app.include_router(admin_panel.router)

app.mount("/disenos", StaticFiles(directory="disenos"), name="disenos")

templates = Jinja2Templates(directory="templates")
app.state.templates = templates

# =========================
# CARGAR VARIABLES DE ENTORNO
# =========================

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ADMIN_USER = os.getenv("ADMIN_USER")
ADMIN_PASS = os.getenv("ADMIN_PASS")

print("SECRET_KEY:", SECRET_KEY)

# ================= DB =================



# ================= CREAR TABLAS =================

@app.on_event("startup")
def crear():
    conn = db()
    c = conn.cursor()

    c.execute("CREATE TABLE IF NOT EXISTS maquinas(id INTEGER PRIMARY KEY,nombre TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS procesos(id INTEGER PRIMARY KEY,maquina_id INTEGER,nombre TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS actividades(id INTEGER PRIMARY KEY,proceso_id INTEGER,nombre TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS operarios(id INTEGER PRIMARY KEY,nombre TEXT)")

    c.execute("""
    CREATE TABLE IF NOT EXISTS ordenes(
        id INTEGER PRIMARY KEY,
        maquina_id INTEGER,
        cantidad INTEGER,
        estado TEXT,
        porcentaje REAL DEFAULT 0
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS orden_actividades(
        id INTEGER PRIMARY KEY,
        orden_id INTEGER,
        actividad_id INTEGER,
        cantidad_total INTEGER,
        cantidad_realizada INTEGER DEFAULT 0
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS registros_produccion(
        id INTEGER PRIMARY KEY,
        operario_id INTEGER,
        orden_id INTEGER,
        actividad_id INTEGER,
        cantidad INTEGER,
        inicio TEXT,
        fin TEXT,
        tiempo INTEGER
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS bonos(
        id INTEGER PRIMARY KEY,
        operario_id INTEGER,
        actividad_id INTEGER,
        unidades INTEGER,
        horas REAL,
        rendimiento REAL,
        porcentaje REAL,
        valor REAL,
        fecha TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS estandares_actividad(
        id INTEGER PRIMARY KEY,
        actividad_id INTEGER,
        unidades_por_hora REAL,
        costo_mo_unidad REAL,
        costo_mo_hora REAL
    )
    """)


    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL
    )
    """)

    # Índice para velocidad
    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_movimientos_referencia
    ON movimientos_inventario(referencia)
    """)

        # Crear admin inicial si no existe
    c.execute("SELECT * FROM users WHERE username = ?", ("admin",))
    existe = c.fetchone()

    if not existe:
        hashed = hash_password("1234")  # cambia por tu contraseña real
        c.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            ("admin", hashed, "admin")
        )

    conn.commit()
    conn.close()

# ================= HOME =================

@app.get("/", response_class=HTMLResponse)
def home(request: Request):

    if not require_admin(request):
        return RedirectResponse("/admin", 303)

    conn = db()
    c = conn.cursor()

    # Órdenes activas
    ordenes_activas = c.execute("""
        SELECT COUNT(*) FROM ordenes
        WHERE estado='ABIERTA'
    """).fetchone()[0]

    # Producción hoy
    produccion_hoy = c.execute("""
        SELECT SUM(cantidad)
        FROM registros_produccion
        WHERE date(inicio)=date('now')
    """).fetchone()[0] or 0

    # Operarios activos hoy
    operarios_activos = c.execute("""
        SELECT COUNT(DISTINCT operario_id)
        FROM registros_produccion
        WHERE date(inicio)=date('now')
    """).fetchone()[0] or 0

    # Avance promedio
    row = c.execute("""
        SELECT SUM(cantidad_realizada),
               SUM(cantidad_total)
        FROM orden_actividades
    """).fetchone()

    if row and row[1] and row[1] > 0:
        avance_promedio = round((row[0] / row[1]) * 100, 1)
    else:
        avance_promedio = 0

    conn.close()

    return templates.TemplateResponse("home.html", {
        "request": request,
        "ordenes_activas": ordenes_activas,
        "produccion_hoy": produccion_hoy,
        "avance_promedio": avance_promedio,
        "operarios_activos": operarios_activos
    })
# ================= PANEL =================

@app.get("/panel", response_class=HTMLResponse)
def panel(request: Request):

    # 🔐 PROTECCIÓN DE SESIÓN
    if not require_admin(request):
        return RedirectResponse("/admin",303)

    conn = db()
    c = conn.cursor()

    maquinas = c.execute("SELECT id,nombre FROM maquinas").fetchall()

    ordenes_sql = c.execute("""
        SELECT o.id,
               m.nombre,
               o.cantidad,
               o.estado,
               o.cerrado_en
        FROM ordenes o
        JOIN maquinas m ON m.id=o.maquina_id
        ORDER BY o.id DESC
    """).fetchall()

    ordenes = []

    for o in ordenes_sql:

        oid = o[0]
        producto = o[1]
        cantidad = o[2]
        estado = o[3]
        cerrado = o[4]

        # ---- PORCENTAJE DINÁMICO ----
        c.execute("""
            SELECT SUM(cantidad_realizada),
                   SUM(cantidad_total)
            FROM orden_actividades
            WHERE orden_id=?
        """,(oid,))

        row_pct = c.fetchone()

        if row_pct and row_pct[1] and row_pct[1] > 0:
            porcentaje_general = round((row_pct[0] / row_pct[1]) * 100, 2)
        else:
            porcentaje_general = 0

        # ---- ACTIVIDADES ----
        acts = c.execute("""
            SELECT 
                p.nombre,
                a.nombre,
                oa.cantidad_realizada,
                oa.cantidad_total
            FROM orden_actividades oa
            JOIN actividades a ON a.id = oa.actividad_id
            JOIN procesos p ON p.id = a.proceso_id
            WHERE oa.orden_id = ?
            ORDER BY p.id
        """,(oid,)).fetchall()

        procesos = {}

        for pr, act, real, total in acts:

            if pr not in procesos:
                procesos[pr] = []

            pct = int((real/total)*100) if total else 0

            procesos[pr].append({
                "nombre": act,
                "realizada": real,
                "total": total,
                "porcentaje": pct
            })

        ordenes.append({
            "id": oid,
            "producto": producto,
            "cantidad": cantidad,
            "estado": estado,
            "porcentaje": porcentaje_general,
            "cerrado_en": cerrado,
            "procesos":[
                {"nombre":k,"actividades":v}
                for k,v in procesos.items()
            ]
        })

    conn.close()

    return templates.TemplateResponse("panel.html",{
        "request":request,
        "maquinas":maquinas,
        "ordenes":ordenes
    })

# ================= METRICAS OPERARIOS =================

from fastapi.responses import HTMLResponse # type: ignore

@app.get("/metricas_operarios", response_class=HTMLResponse)
def metricas_operarios(request: Request):

    conn = db()
    c = conn.cursor()

    # ===== RESUMEN AGRUPADO POR OPERARIO =====
    resumen = c.execute("""
    SELECT 
        op.nombre,
        SUM(r.cantidad) as unidades,
        SUM(strftime('%s',r.fin)-strftime('%s',r.inicio)) as segundos,
        COUNT(r.id) as operaciones
    FROM registros_produccion r
    JOIN operarios op ON op.id = r.operario_id
    GROUP BY op.nombre
    ORDER BY unidades DESC
    """).fetchall()

    resumen_final = []

    for nombre, unidades, segundos, operaciones in resumen:
        segundos = segundos or 0
        horas = round(segundos / 3600,2) if segundos else 0
        productividad = round(unidades / horas,2) if horas else 0

        resumen_final.append((nombre, unidades, horas, productividad, operaciones))

    # ===== DETALLE =====
    detalle = c.execute("""
    SELECT op.nombre,
           a.nombre,
           r.cantidad,
           r.inicio,
           r.fin
    FROM registros_produccion r
    JOIN operarios op ON op.id=r.operario_id
    JOIN actividades a ON a.id=r.actividad_id
    ORDER BY r.id DESC
    """).fetchall()

    conn.close()

    return templates.TemplateResponse("Metricas.html",{
        "request":request,
        "resumen":resumen_final,
        "detalle":detalle
    })

# ================= KPI DASHBOARD =================

@app.get("/kpi", response_class=HTMLResponse)
def kpi(request: Request):

    if not require_admin(request):
        return RedirectResponse("/admin",303)

    conn = db()
    c = conn.cursor()

    # KPI 1: piezas por operario
    por_operario = c.execute("""
    SELECT o.nombre,
           IFNULL(SUM(r.cantidad),0)
    FROM registros_produccion r
    JOIN operarios o ON o.id=r.operario_id
    GROUP BY o.id
    """).fetchall()

    # KPI 2: minutos trabajados por operario
    minutos = c.execute("""
    SELECT o.nombre,
           IFNULL(SUM((julianday(r.fin)-julianday(r.inicio))*24*60),0)
    FROM registros_produccion r
    JOIN operarios o ON o.id=r.operario_id
    GROUP BY o.id
    """).fetchall()

    # KPI 3: producción diaria
    diario = c.execute("""
    SELECT substr(inicio,1,10),
           SUM(cantidad)
    FROM registros_produccion
    GROUP BY substr(inicio,1,10)
    ORDER BY substr(inicio,1,10)
    """).fetchall()

    conn.close()

    return templates.TemplateResponse("kpi.html",{
        "request":request,
        "por_operario":por_operario,
        "minutos":minutos,
        "diario":diario
    })

# ================= CREAR ORDEN DESDE PANEL =================

@app.post("/crear_orden_web")
def crear_orden_web(cantidad: int = Form(...), maquina: int = Form(...)):

    conn = db()
    c = conn.cursor()

    # crear orden principal
    c.execute("""
        INSERT INTO ordenes(maquina_id,cantidad,estado)
        VALUES(?,?, 'ABIERTA')
    """,(maquina,cantidad))

    orden_id = c.lastrowid

    # tomar actividades asociadas a esa maquina
    c.execute("""
        SELECT a.id
        FROM actividades a
        JOIN procesos p ON a.proceso_id = p.id
        WHERE p.maquina_id = ?
    """,(maquina,))

    acts = c.fetchall()

    for a in acts:
        c.execute("""
            INSERT INTO orden_actividades
            (orden_id,actividad_id,cantidad_total,cantidad_realizada)
            VALUES(?,?,?,0)
        """,(orden_id,a[0],cantidad))

    conn.commit()
    conn.close()

    return RedirectResponse("/panel",303)


# ================= REGISTRO =================

@app.post("/registro")
def registro(data: dict):

    inicio = datetime.fromisoformat(data["inicio"])
    fin = datetime.fromisoformat(data["fin"])
    tiempo = int((fin - inicio).total_seconds())

    conn = db()
    c = conn.cursor()

    c.execute("""
        INSERT INTO registros_produccion
        VALUES(NULL,?,?,?,?,?,?,?)
    """, (
        data["operario_id"],
        data["orden_id"],
        data["actividad_id"],
        data["cantidad"],
        data["inicio"],
        data["fin"],
        tiempo
    ))

    c.execute("""
        UPDATE orden_actividades
        SET cantidad_realizada = cantidad_realizada + ?
        WHERE orden_id=? AND actividad_id=?
    """, (
        data["cantidad"],
        data["orden_id"],
        data["actividad_id"]
    ))

    # ---- CALCULAR PORCENTAJE BASADO EN EMPAQUE ----
    c.execute("""
        SELECT 
            SUM(oa.cantidad_realizada),
            SUM(oa.cantidad_total)
        FROM orden_actividades oa
        JOIN actividades a ON a.id = oa.actividad_id
        WHERE oa.orden_id=? 
        AND a.nombre LIKE '%Empaque%'
    """, (data["orden_id"],))

    row = c.fetchone()

    if row and row[1] and row[1] > 0:
        porcentaje = round((row[0] / row[1]) * 100, 2)
    else:
        porcentaje = 0

    c.execute("""
        UPDATE ordenes
        SET porcentaje=?,
            estado=CASE WHEN ? >= 100 THEN 'CERRADA' ELSE estado END
        WHERE id=?
    """, (porcentaje, porcentaje, data["orden_id"]))

    conn.commit()
    conn.close()

    return {"ok": True, "porcentaje": porcentaje}

# ================= EXPORTAR =================

@app.get("/exportar_excel")
def exportar_excel():

    conn = db()
    c = conn.cursor()

    rows = c.execute("""
    SELECT o.nombre,a.nombre,r.cantidad,r.inicio,r.fin
    FROM registros_produccion r
    JOIN operarios o ON o.id=r.operario_id
    JOIN actividades a ON a.id=r.actividad_id
    """).fetchall()

    wb = Workbook()
    ws = wb.active

    ws.append(["Operario","Actividad","Cantidad","Inicio","Fin"])

    for r in rows:
        ws.append(r)

    path="reporte_produccion.xlsx"
    wb.save(path)

    conn.close()

    return FileResponse(path,filename="reporte_produccion.xlsx")

# ================= ELIMINAR ORDEN =================

@app.get("/eliminar/{id}")
def eliminar(id: int):

    conn = db()
    c = conn.cursor()

    # borrar actividades de la orden
    c.execute("DELETE FROM orden_actividades WHERE orden_id=?", (id,))

    # borrar orden principal
    c.execute("DELETE FROM ordenes WHERE id=?", (id,))

    conn.commit()
    conn.close()

    return RedirectResponse("/panel",303)


# ================= CERRAR ORDEN =================

@app.get("/cerrar/{orden_id}")
def cerrar_orden(orden_id: int):

    conn = db()
    c = conn.cursor()

    # 1️⃣ Marcar todas las actividades como completadas
    c.execute("""
        UPDATE orden_actividades
        SET cantidad_realizada = cantidad_total
        WHERE orden_id=?
    """, (orden_id,))

    # 2️⃣ Marcar orden como cerrada
    c.execute("""
        UPDATE ordenes
        SET estado='CERRADA',
            cerrado_en=?
        WHERE id=?
    """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), orden_id))

    conn.commit()
    conn.close()

    return RedirectResponse("/panel", status_code=303)

@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/admin")
def admin_post(request: Request, user: str = Form(...), password: str = Form(...)):

    if login_user(request, user, password):

        next_page = request.query_params.get("next")

        if next_page:
            return RedirectResponse(f"/{next_page}", status_code=303)

        return RedirectResponse("/", status_code=303)

    return "Credenciales incorrectas"



# ================= REGISTRO PRODUCCION ANDROID =================

@app.post("/registro_android")
def registro_android(data: dict):

    conn = db()
    c = conn.cursor()

    tiempo = int(data.get("tiempo", 0))

    fin = datetime.now()
    inicio = fin - timedelta(seconds=tiempo)

    c.execute("""
    INSERT INTO registros_produccion
    (operario_id, orden_id, actividad_id, cantidad, inicio, fin, tiempo)
    VALUES (?,?,?,?,?,?,?)
    """,(
        data["operario_id"],
        data["orden_id"],
        data["actividad_id"],
        data["cantidad"],
        inicio.strftime("%Y-%m-%d %H:%M:%S"),
        fin.strftime("%Y-%m-%d %H:%M:%S"),
        tiempo
    ))

    # actualizar actividad
    c.execute("""
    UPDATE orden_actividades
    SET cantidad_realizada = cantidad_realizada + ?
    WHERE orden_id=? AND actividad_id=?
    """,(
        data["cantidad"],
        data["orden_id"],
        data["actividad_id"]
    ))

    # ---- RECALCULAR PORCENTAJE GENERAL DE LA ORDEN ----
    c.execute("""
        SELECT SUM(cantidad_realizada),
               SUM(cantidad_total)
        FROM orden_actividades
        WHERE orden_id=?
    """,(data["orden_id"],))

    row = c.fetchone()

    if row and row[1] and row[1] > 0:
        porcentaje = round((row[0] / row[1]) * 100, 2)
    else:
        porcentaje = 0

    c.execute("""
        UPDATE ordenes
        SET porcentaje=?,
            estado=CASE WHEN ? >= 100 THEN 'CERRADA' ELSE estado END
        WHERE id=?
    """,(porcentaje, porcentaje, data["orden_id"]))

    conn.commit()
    conn.close()

    return {"status":"ok"}

# ================= ANDROID REST =================

@app.get("/importar")
def importar(request: Request):
    return templates.TemplateResponse("importar.html", {
        "request": request
    })

@app.get("/operarios")
def operarios():
    c=db().cursor()
    return c.execute("SELECT id,nombre FROM operarios").fetchall()

@app.get("/maquinas")
def maquinas():
    c=db().cursor()
    return c.execute("SELECT id,nombre FROM maquinas").fetchall()

@app.get("/ordenes")
def ordenes_android():
    c=db().cursor()
    return c.execute("""
    SELECT id,maquina_id,estado,porcentaje
    FROM ordenes
    WHERE estado!='CERRADA'
    """).fetchall()

@app.get("/procesos/{orden_id}")
def procesos_android(orden_id:int):
    c=db().cursor()
    return c.execute("""
    SELECT DISTINCT p.id,p.nombre
    FROM orden_actividades oa
    JOIN actividades a ON a.id=oa.actividad_id
    JOIN procesos p ON p.id=a.proceso_id
    WHERE oa.orden_id=?
    """,(orden_id,)).fetchall()

    conn.close()
    return rows

@app.get("/actividades/{orden}/{proceso}")
def actividades_android(orden:int, proceso:int):
    c=db().cursor()
    return c.execute("""
    SELECT a.id,a.nombre
    FROM orden_actividades oa
    JOIN actividades a ON a.id=oa.actividad_id
    WHERE oa.orden_id=? AND a.proceso_id=?
    """,(orden,proceso)).fetchall()

    conn.close()
    return rows

@app.get("/limpiar_registros")
def limpiar_registros():
    conn = db()
    c = conn.cursor()

    c.execute("DELETE FROM registros_produccion")
    conn.commit()
    conn.close()

    return {"ok": True}

@app.get("/metricas", response_class=HTMLResponse)
def metricas(request:Request):

    conn = db()
    c = conn.cursor()

    # -------- RESUMEN POR OPERARIO --------
    resumen = c.execute("""
    SELECT o.nombre,
           SUM(r.cantidad) as unidades,
           SUM((strftime('%s',r.fin)-strftime('%s',r.inicio))/60.0) as minutos
    FROM registros_produccion r
    JOIN operarios o ON o.id=r.operario_id
    GROUP BY o.nombre
    ORDER BY unidades DESC
    """).fetchall()


    # -------- DETALLE COMPLETO --------
    detalle = c.execute("""
    SELECT o.nombre,
           a.nombre,
           r.cantidad,
           r.inicio,
           r.fin
    FROM registros_produccion r
    JOIN operarios o ON o.id=r.operario_id
    JOIN actividades a ON a.id=r.actividad_id
    ORDER BY r.id DESC
    """).fetchall()

    conn.close()

    return templates.TemplateResponse("Metricas.html",{
        "request":request,
        "resumen":resumen,
        "detalle":detalle
    })

#IMPORTAR EXCEL NUEVO#

@app.post("/importar_excel")
async def importar_excel(
    maquinas: UploadFile = File(...),
    procesos: UploadFile = File(...),
    actividades: UploadFile = File(...),
    operarios: UploadFile = File(...)
):

    conn = db()
    c = conn.cursor()

    df_maquinas = pd.read_excel(maquinas.file)
    df_procesos = pd.read_excel(procesos.file)
    df_actividades = pd.read_excel(actividades.file)
    df_operarios = pd.read_excel(operarios.file)

    # ---------- MAQUINAS ----------
    for _, row in df_maquinas.iterrows():
        c.execute("INSERT INTO maquinas(nombre) VALUES(?)",(row["nombre"],))

    # ---------- PROCESOS ----------
    for _, row in df_procesos.iterrows():

        mid = c.execute(
            "SELECT id FROM maquinas WHERE nombre=?",
            (row["maquina"],)
        ).fetchone()

        if mid:
            c.execute(
                "INSERT INTO procesos(maquina_id,nombre) VALUES(?,?)",
                (mid[0], row["nombre"])
            )

    # ---------- ACTIVIDADES ----------
    for _, row in df_actividades.iterrows():

        pid = c.execute(
            "SELECT id FROM procesos WHERE nombre=?",
            (row["proceso"],)
        ).fetchone()

        if pid:
            c.execute(
                "INSERT INTO actividades(proceso_id,nombre) VALUES(?,?)",
                (pid[0], row["nombre"])
            )

    # ---------- OPERARIOS ----------
    for _, row in df_operarios.iterrows():
        c.execute("INSERT INTO operarios(nombre) VALUES(?)",(row["nombre"],))

    conn.commit()
    conn.close()

    return RedirectResponse("/",303)

#RESETEAR BASE#

@app.get("/resetear_base")
def resetear_base():

    conn = db()
    c = conn.cursor()

    # Orden correcto (hijos → padres)
    c.execute("DELETE FROM registros_produccion")
    c.execute("DELETE FROM actividades")
    c.execute("DELETE FROM procesos")
    c.execute("DELETE FROM maquinas")
    c.execute("DELETE FROM operarios")

    # Resetear autoincrement (opcional pero recomendado)
    c.execute("DELETE FROM sqlite_sequence")

    conn.commit()
    conn.close()

    return RedirectResponse("/", status_code=303)

@app.get("/reset_metricas")
def reset_metricas():

    conn = db()
    c = conn.cursor()

    c.execute("DELETE FROM registros_produccion")
    c.execute("DELETE FROM bonos")
    c.execute("UPDATE ordenes SET porcentaje=0, estado='ABIERTA', cerrado_en=NULL")
    c.execute("UPDATE orden_actividades SET cantidad_realizada=0")

    conn.commit()
    conn.close()

    return RedirectResponse("/",303)

@app.get("/borrar_registros")
def borrar_registros():

    conn = db()
    c = conn.cursor()

    c.execute("DELETE FROM registros_produccion")

    conn.commit()
    conn.close()

    return {"ok":True}

@app.get("/limpiar_excel")
def limpiar_excel(request: Request):

    # proteger solo admin
    if not require_admin(request):
        return RedirectResponse("/admin",303)

    conn = db()
    c = conn.cursor()

    # borrar producción
    c.execute("DELETE FROM registros_produccion")
    c.execute("DELETE FROM orden_actividades")
    c.execute("DELETE FROM ordenes")

    # borrar datos importados
    c.execute("DELETE FROM actividades")
    c.execute("DELETE FROM procesos")
    c.execute("DELETE FROM maquinas")
    c.execute("DELETE FROM operarios")

    conn.commit()
    conn.close()

    return RedirectResponse("/",303)

@app.get("/ver_actividades")
def ver_actividades():
    conn = db()
    c = conn.cursor()
    rows = c.execute("SELECT id, nombre FROM actividades").fetchall()
    conn.close()
    return rows

@app.get("/insertar_estandares_demo")
def insertar_estandares_demo():
    conn = db()
    c = conn.cursor()

    # ejemplo
    c.execute("INSERT INTO estandares_actividad (actividad_id, unidades_por_hora) VALUES (1, 12)")
    c.execute("INSERT INTO estandares_actividad (actividad_id, unidades_por_hora) VALUES (2, 8)")
    c.execute("INSERT INTO estandares_actividad (actividad_id, unidades_por_hora) VALUES (3, 15)")

    conn.commit()
    conn.close()

    return {"ok": True}

META_MENSUAL = 5000
TARIFA_HH = 10000   # ajustable

@app.get("/ver_bonos")
def ver_bonos():
    conn = db()
    c = conn.cursor()
    rows = c.execute("""
    SELECT o.nombre,a.nombre,b.unidades,b.horas,b.rendimiento,b.porcentaje,b.valor
    FROM bonos b
    JOIN operarios o ON o.id=b.operario_id
    JOIN actividades a ON a.id=b.actividad_id
    """).fetchall()
    conn.close()
    return rows

@app.get("/ver_registros")
def ver_registros():
    conn = db()
    c = conn.cursor()
    rows = c.execute("SELECT * FROM registros_produccion").fetchall()
    conn.close()
    return rows

@app.get("/insertar_estandar_3")
def insertar_estandar_3():
    conn = db()
    c = conn.cursor()

    # actividad 3 = Pintura Despulpadora 2.5
    # cambia 20 por el valor real de tu Excel (unidades por hora)
    c.execute("""
    INSERT INTO estandares_actividad (actividad_id, unidades_por_hora)
    VALUES (3, 20)
    """)

    conn.commit()
    conn.close()
    return {"ok": True}

def bonos_mes(mes, anio):

    conn = db()
    c = conn.cursor()

    rows = c.execute("""
        SELECT
            o.id,
            o.nombre,
            SUM(r.cantidad) as unidades,
            SUM((strftime('%s', r.fin) - strftime('%s', r.inicio)) / 3600.0) as horas,
            COUNT(DISTINCT date(r.inicio)) as dias_trabajados
        FROM registros_produccion r
        JOIN operarios o ON o.id = r.operario_id
        WHERE strftime('%m', r.inicio) = ?
        AND strftime('%Y', r.inicio) = ?
        GROUP BY o.id, o.nombre
    """, (f"{mes:02d}", str(anio))).fetchall()

    resultado = []

    for operario_id, nombre, unidades, horas, dias in rows:

        if not horas or horas == 0:
            continue

        # 🔹 Horas disponibles (530 minutos por día)
        horas_disponibles = (dias * 530) / 60
        eficiencia_ocupacion = horas / horas_disponibles if horas_disponibles > 0 else 0

        # 🔹 Obtener estándar promedio del operario en el mes
        est = c.execute("""
            SELECT AVG(e.unidades_por_hora),
                   AVG(e.costo_mo_unidad)
            FROM registros_produccion r
            JOIN estandares_actividad e ON e.actividad_id = r.actividad_id
            WHERE r.operario_id = ?
            AND strftime('%m', r.inicio) = ?
            AND strftime('%Y', r.inicio) = ?
        """, (operario_id, f"{mes:02d}", str(anio))).fetchone()

        if not est or not est[0]:
            continue

        unidades_estandar = est[0]
        costo_base = est[1] or 0

        # 🔹 Eficiencia productiva
        rendimiento_real = unidades / horas
        eficiencia_productiva = rendimiento_real / unidades_estandar

        # 🔹 Determinar porcentaje bono
        if eficiencia_productiva >= 1.10:
            porcentaje = 0.04
        elif eficiencia_productiva >= 1.00:
            porcentaje = 0.03
        elif eficiencia_productiva >= 0.90:
            porcentaje = 0.02
        else:
            porcentaje = 0

        bono_total = unidades * costo_base * porcentaje

        resultado.append({
            "nombre": nombre,
            "eficiencia_productiva": round(eficiencia_productiva * 100, 2),
            "eficiencia_ocupacion": round(eficiencia_ocupacion * 100, 2),
            "porcentaje_bono": porcentaje * 100,
            "bono_total": round(bono_total, 2)
        })

    conn.close()
    return resultado

import pandas as pd # type: ignore

@app.get("/cargar_estandares_excel")
def cargar_estandares_excel():

    conn = db()
    c = conn.cursor()

    ruta = "excel/estandares.xlsx"
    df = pd.read_excel(ruta)

    c.execute("DELETE FROM estandares_actividad")

    for _, row in df.iterrows():

        actividad_id = int(row["actividad_id"])
        unidades = float(row["unidades_por_hora"])
        costo = float(row["costo_mo_unidad"])

        c.execute("""
            INSERT INTO estandares_actividad
            (actividad_id, unidades_por_hora, costo_mo_unidad, costo_mo_hora)
            VALUES (?, ?, ?, 0)
        """, (actividad_id, unidades, costo))

    conn.commit()
    conn.close()

    return {"estandares_cargados": len(df)}

from fastapi.responses import HTMLResponse # type: ignore
from datetime import datetime

@app.get("/bonos", response_class=HTMLResponse)
def bonos(request: Request):

    if not require_admin(request):
        return RedirectResponse("/admin", 303)

    hoy = datetime.now()

    mes = int(request.query_params.get("mes", hoy.month))
    anio = int(request.query_params.get("anio", hoy.year))

    datos = bonos_mes(mes, anio)

    print("RESULTADO BONOS:", datos)

    return templates.TemplateResponse("bonos.html", {
        "request": request,
        "datos": datos,
        "mes": mes,
        "anio": anio
    })

#INVENTARIO#

def formato_cop(valor):
    return "${:,.0f}".format(valor).replace(",", ".")

@app.get("/inventario", response_class=HTMLResponse)
def inventario(request: Request):

    if not require_admin(request):
        return RedirectResponse("/admin", 303)

    conn = db()
    c = conn.cursor()

    productos = c.execute("""
        SELECT referencia,
               cantidad_total,
               entregadas,
               total_disponibles,
               peso_unitario_gr,
               precio_unitario
        FROM inventario
    """).fetchall()

    inventario_final = []

    total_refs = 0
    valor_total_general = 0
    peso_total_general = 0
    bajo_stock_count = 0

    for p in productos:
        ref = p[0]
        cantidad_total = p[1] or 0
        entregadas = p[2] or 0
        disponibles = p[3] or 0
        peso_unitario = p[4] or 0
        precio_unitario = p[5] or 0

        peso_total = (disponibles * peso_unitario) / 1000
        valor_total = disponibles * precio_unitario

        bajo_stock = disponibles <= STOCK_MINIMO

        if bajo_stock:
            bajo_stock_count += 1

        total_refs += 1
        valor_total_general += valor_total
        peso_total_general += peso_total

        inventario_final.append({
            "referencia": ref,
             "cantidad_total": cantidad_total,
            "entregadas": entregadas,
            "disponibles": disponibles,
            "peso_total": peso_total,
            "precio": precio_unitario,
            "valor_total": valor_total,
            "bajo_stock": bajo_stock
        })

    conn.close()

    return templates.TemplateResponse("inventario.html",{
        "request":request,
        "inventario":inventario_final,
        "total_refs": total_refs,
        "valor_total": valor_total_general,
        "peso_total": peso_total_general,
        "bajo_stock_count": bajo_stock_count
    })

@app.post("/inventario/movimiento")
def registrar_movimiento(
    referencia: str = Form(...),
    tipo: str = Form(...),
    cantidad: int = Form(...),
    request: Request = None
):

    if not require_admin(request):
        return RedirectResponse("/admin", 303)

    conn = db()
    c = conn.cursor()

    # 🔎 Calcular stock actual
    c.execute("""
        SELECT 
            SUM(CASE WHEN tipo='INGRESO' THEN cantidad ELSE 0 END),
            SUM(CASE WHEN tipo='SALIDA' THEN cantidad ELSE 0 END)
        FROM movimientos_inventario
        WHERE referencia=?
    """, (referencia,))

    row = c.fetchone()

    ingresos = row[0] or 0
    salidas = row[1] or 0
    stock_actual = ingresos - salidas

    # 🚨 Validar salida
    if tipo == "SALIDA" and cantidad > stock_actual:
        conn.close()
        return "Error: Stock insuficiente"

    # 🚫 Validar negativos
    if cantidad <= 0:
        conn.close()
        return "Error: Cantidad inválida"

    # ✅ Registrar movimiento
    c.execute("""
        INSERT INTO movimientos_inventario
        (referencia, tipo, cantidad, usuario)
        VALUES (?,?,?,?)
    """, (referencia, tipo, cantidad, "ADMIN"))

    conn.commit()
    conn.close()

    return RedirectResponse("/inventario", 303)

from fastapi import UploadFile, File
import pandas as pd # type: ignore

@app.post("/inventario/importar")
async def importar_inventario(
    file: UploadFile = File(...),
    request: Request = None
):

    if not require_admin(request):
        return RedirectResponse("/admin", 303)

    df = pd.read_excel(file.file)
    df.columns = df.columns.str.strip()

    conn = db()
    c = conn.cursor()

    # 🔥 Limpia inventario y movimientos
    c.execute("DELETE FROM movimientos_inventario")
    c.execute("DELETE FROM inventario")

    usuario = request.session.get("username")

    for _, row in df.iterrows():

        referencia = str(row["Referencia"]).strip()
        peso = float(row["Peso unitario (gr)"] or 0)
        disponibles = int(row["Disponibles"] or 0)
        precio = float(row["Precio unitario"] or 0)

        cantidad_total = disponibles
        entregadas = 0
        total_disponibles = disponibles

        # Insertar producto
        c.execute("""
            INSERT INTO inventario
            (referencia, peso_unitario_gr, cantidad_total,
             entregadas, total_disponibles, precio_unitario)
            VALUES (?,?,?,?,?,?)
        """, (
            referencia,
            peso,
            cantidad_total,
            entregadas,
            total_disponibles,
            precio
        ))

        # 🔥 Crear movimiento inicial automático
        c.execute("""
            INSERT INTO movimientos_inventario
            (referencia, tipo, cantidad, usuario)
            VALUES (?,?,?,?)
        """, (
            referencia,
            "INGRESO",
            disponibles,
            f"{usuario} (IMPORTACION INICIAL)"
        ))

    conn.commit()
    conn.close()

    return RedirectResponse("/inventario", 303)

@app.get("/bonos/detalle", response_class=HTMLResponse)
def detalle_bono(request: Request):

    if not require_admin(request):
        return RedirectResponse("/admin", 303)

    nombre = request.query_params.get("nombre")
    mes = int(request.query_params.get("mes"))
    anio = int(request.query_params.get("anio"))

    conn = db()
    c = conn.cursor()

    rows = c.execute("""
        SELECT 
            a.id,
            a.nombre,
            SUM(r.cantidad) as unidades,
            SUM((strftime('%s', r.fin) - strftime('%s', r.inicio)) / 3600.0) as horas
        FROM registros_produccion r
        JOIN operarios o ON o.id = r.operario_id
        JOIN actividades a ON a.id = r.actividad_id
        WHERE o.nombre = ?
        AND strftime('%m', r.inicio) = ?
        AND strftime('%Y', r.inicio) = ?
        GROUP BY a.id, a.nombre
    """, (nombre, f"{mes:02d}", str(anio))).fetchall()

    detalle = []
    total_bono = 0

    for actividad_id, actividad, unidades, horas in rows:

        horas = horas or 0
        unidades = unidades or 0

        rendimiento_real = (unidades / horas) if horas > 0 else 0

        est = c.execute("""
            SELECT unidades_por_hora, costo_mo_unidad
            FROM estandares_actividad
            WHERE actividad_id = ?
        """, (actividad_id,)).fetchone()

        if not est:
            continue

        unidades_estandar, costo_base = est

        eficiencia = rendimiento_real / unidades_estandar if unidades_estandar else 0

        if eficiencia >= 1.10:
            porcentaje = 0.04
        elif eficiencia >= 1.00:
            porcentaje = 0.03
        elif eficiencia >= 0.90:
            porcentaje = 0.02
        else:
            porcentaje = 0

        bono = unidades * costo_base * porcentaje
        total_bono += bono

        detalle.append({
            "actividad": actividad,
            "unidades": unidades,
            "horas": round(horas,2),
            "rendimiento": round(rendimiento_real,2),
            "estandar": unidades_estandar,
            "eficiencia": round(eficiencia*100,2),
            "porcentaje": porcentaje*100,
            "bono": round(bono,2)
        })

    conn.close()

    return templates.TemplateResponse("bono_detalle.html",{
        "request":request,
        "nombre":nombre,
        "mes":mes,
        "anio":anio,
        "detalle":detalle,
        "total_bono": round(total_bono,2)
    })

from dotenv import load_dotenv
import os

load_dotenv()  # automáticamente busca .env

SECRET_KEY = os.getenv("SECRET_KEY")

#USUARIOS#

@app.get("/usuarios", response_class=HTMLResponse)
def ver_usuarios(request: Request):

    if not require_admin(request):
        return RedirectResponse("/admin", status_code=303)

    conn = db()
    c = conn.cursor()
    c.execute("SELECT id, username, role FROM users")
    usuarios = c.fetchall()
    conn.close()

    return templates.TemplateResponse("usuarios.html", {
        "request": request,
        "usuarios": usuarios
    })

@app.post("/usuarios/crear")
def crear_usuario(request: Request, username: str = Form(...), password: str = Form(...), role: str = Form(...)):

    if not require_admin(request):
        return RedirectResponse("/admin", status_code=303)

    hashed = hash_password(password)

    conn = db()
    c = conn.cursor()

    try:
        c.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            (username, hashed, role)
        )
        conn.commit()
    except:
        pass

    conn.close()

    return RedirectResponse("/usuarios", status_code=303)

@app.get("/usuarios/eliminar/{user_id}")
def eliminar_usuario(request: Request, user_id: int):

    if not require_admin(request):
        return RedirectResponse("/admin", status_code=303)

    conn = db()
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    return RedirectResponse("/usuarios", status_code=303)

@app.get("/api/inventario")
def api_inventario():

    conn = sqlite3.connect("produccion.db")
    c = conn.cursor()

    data = c.execute("""
        SELECT 
            i.referencia,

            IFNULL(SUM(
                CASE 
                    WHEN m.tipo='INGRESO' THEN m.cantidad
                    WHEN m.tipo='SALIDA' THEN -m.cantidad
                END
            ),0) as stock

        FROM inventario i

        LEFT JOIN movimientos_inventario m
        ON i.referencia = m.referencia

        GROUP BY i.referencia

        ORDER BY i.referencia

    """).fetchall()

    conn.close()

    return [
        {"referencia": r, "stock": s}
        for r,s in data
    ]

@app.get("/api/kardex/{referencia}")
def api_kardex(referencia: str):

    conn = sqlite3.connect("produccion.db")
    c = conn.cursor()

    data = c.execute("""
        SELECT fecha, tipo, cantidad, saldo
        FROM kardex
        WHERE referencia = ?
        ORDER BY fecha DESC
    """, (referencia,)).fetchall()

    conn.close()

    return [
        {
            "fecha": r[0],
            "tipo": r[1],
            "cantidad": r[2],
            "saldo": r[3]
        }
        for r in data
    ]

@app.get("/materiales_maquinas", response_class=HTMLResponse)
def materiales_maquinas(request: Request):

    conn = db()
    c = conn.cursor()

    maquinas = c.execute("""
        SELECT id, nombre
        FROM maquinas
        ORDER BY nombre
    """).fetchall()

    conn.close()

    return templates.TemplateResponse(
        "materiales_maquinas.html",
        {
            "request": request,
            "maquinas": maquinas
        }
    )

@app.get("/materiales_maquina/{maquina_id}", response_class=HTMLResponse)
def materiales_maquina(maquina_id: int, request: Request):

    conn = db()
    c = conn.cursor()

    maquina = c.execute("""
        SELECT nombre
        FROM maquinas
        WHERE id = ?
    """,(maquina_id,)).fetchone()

    materiales = c.execute("""
        SELECT referencia, cantidad
        FROM maquina_materiales
        WHERE maquina = ?
    """,(maquina_id,)).fetchall()

    inventario = c.execute("""
        SELECT referencia
        FROM inventario
        ORDER BY referencia
    """).fetchall()

    conn.close()

    return templates.TemplateResponse(
        "materiales_maquina.html",
        {
            "request": request,
            "maquina": maquina,
            "maquina_id": maquina_id,
            "materiales": materiales,
            "inventario": inventario
        }
    )

@app.post("/materiales_maquina/{maquina_id}/agregar")
def agregar_material(maquina_id: int,
                     referencia: str = Form(...),
                     cantidad: float = Form(...)):

    conn = db()
    c = conn.cursor()

    c.execute("""
        INSERT INTO maquina_materiales
        (maquina, referencia, cantidad)
        VALUES (?,?,?)
    """,(maquina_id, referencia, cantidad))

    conn.commit()
    conn.close()

    return RedirectResponse(
        f"/materiales_maquina/{maquina_id}",
        status_code=303
    )

import os

@app.get("/api/disenos")
def obtener_disenos():

    carpeta = "disenos"

    archivos = os.listdir(carpeta)

    pdfs = [f for f in archivos if f.endswith(".pdf")]

    return pdfs


BASE_PATH = "disenos"

@app.get("/explorar")
def explorar(ruta: str = ""):

    path = os.path.join(BASE_PATH, ruta)

    carpetas = []
    archivos = []

    for item in os.listdir(path):

        full = os.path.join(path, item)

        if os.path.isdir(full):
            carpetas.append(item)

        elif item.endswith(".pdf"):
            archivos.append(item)

    return {
        "carpetas": carpetas,
        "archivos": archivos
    }

@app.get("/buscar")
def buscar(q: str):

    resultados = []

    for root, dirs, files in os.walk(BASE_PATH):

        for file in files:

            if file.lower().endswith(".pdf"):

                if q.lower() in file.lower():

                    ruta = os.path.join(root, file)

                    ruta_relativa = ruta.replace(BASE_PATH + "\\", "").replace("\\", "/")

                    resultados.append(ruta_relativa)

    return resultados

import os

def buscar_archivos(base):
    archivos = []

    for root, dirs, files in os.walk(base):
        for f in files:
            if f.endswith(".pdf"):
                ruta = os.path.join(root, f)
                archivos.append(ruta.replace(base + "/", ""))

    return archivos

@app.get("/buscar")
def buscar(q: str = ""):

    base = "disenos"
    resultados = []

    for root, dirs, files in os.walk(base):
        for file in files:
            if file.endswith(".pdf") and q.lower() in file.lower():

                ruta = os.path.join(root, file)
                resultados.append(ruta.replace(base + "/", ""))

    return resultados