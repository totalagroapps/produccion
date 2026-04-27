from fastapi import FastAPI, Request, Form, UploadFile, File, Depends  # type: ignore
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse  # type: ignore
from fastapi.templating import Jinja2Templates  # type: ignore
from starlette.middleware.sessions import SessionMiddleware  # type: ignore
from datetime import datetime, timedelta
from openpyxl import Workbook  # type: ignore
from fastapi.staticfiles import StaticFiles  # type: ignore
from dotenv import load_dotenv
from auth import login_user, require_admin, hash_password
from database import db
from routers.ordenes import router as ordenes_router
from routers.usuarios import router as usuarios_router
from routers.android import router as android_router
from routers.metricas import router as metricas_router
from routers.bonos import router as bonos_router
from routers.admin_tools import router as admin_tools_router
from routers import planificador
from routers import configuracion
from routers import admin_panel

import os
import pandas as pd  # type: ignore

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ADMIN_USER = os.getenv("ADMIN_USER")
ADMIN_PASS = os.getenv("ADMIN_PASS")

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

templates = Jinja2Templates(directory="templates")
app.state.templates = templates

app.include_router(android_router)
app.include_router(metricas_router)
app.include_router(bonos_router)
app.include_router(admin_tools_router)
app.include_router(configuracion.router)
app.include_router(admin_panel.router)
app.include_router(planificador.router)


# ================= CREAR TABLAS =================

@app.on_event("startup")
def crear():
    conn = db()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS maquinas(
        id SERIAL PRIMARY KEY,
        nombre TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS procesos(
        id SERIAL PRIMARY KEY,
        maquina_id INTEGER,
        nombre TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS actividades(
        id SERIAL PRIMARY KEY,
        proceso_id INTEGER,
        nombre TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS operarios(
        id SERIAL PRIMARY KEY,
        nombre TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS ordenes(
        id SERIAL PRIMARY KEY,
        maquina_id INTEGER,
        cantidad INTEGER,
        estado TEXT,
        porcentaje REAL DEFAULT 0,
        cerrado_en TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS orden_actividades(
        id SERIAL PRIMARY KEY,
        orden_id INTEGER,
        actividad_id INTEGER,
        cantidad_total INTEGER,
        cantidad_realizada INTEGER DEFAULT 0
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS registros_produccion(
        id SERIAL PRIMARY KEY,
        operario_id INTEGER,
        orden_id INTEGER,
        actividad_id INTEGER,
        cantidad INTEGER,
        inicio TEXT,
        fin TEXT,
        tiempo INTEGER
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS bonos(
        id SERIAL PRIMARY KEY,
        operario_id INTEGER,
        actividad_id INTEGER,
        unidades INTEGER,
        horas REAL,
        rendimiento REAL,
        porcentaje REAL,
        valor REAL,
        fecha TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS estandares_actividad(
        id SERIAL PRIMARY KEY,
        actividad_id INTEGER,
        unidades_por_hora REAL,
        costo_mo_unidad REAL,
        costo_mo_hora REAL
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL
    )""")

    # Crear admin inicial si no existe
    c.execute("SELECT * FROM users WHERE username = %s", ("admin",))
    existe = c.fetchone()

    if not existe:
        hashed = hash_password("1234")
        c.execute(
            "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
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

    c.execute("SELECT COUNT(*) FROM ordenes WHERE estado='ABIERTA'")
    ordenes_activas = c.fetchone()[0]

    c.execute("""
        SELECT COALESCE(SUM(cantidad), 0)
        FROM registros_produccion
        WHERE inicio::date = CURRENT_DATE
    """)
    produccion_hoy = c.fetchone()[0]

    c.execute("""
        SELECT COUNT(DISTINCT operario_id)
        FROM registros_produccion
        WHERE inicio::date = CURRENT_DATE
    """)
    operarios_activos = c.fetchone()[0] or 0

    c.execute("""
        SELECT SUM(cantidad_realizada), SUM(cantidad_total)
        FROM orden_actividades
    """)
    row = c.fetchone()

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

    if not require_admin(request):
        return RedirectResponse("/admin", 303)

    conn = db()
    c = conn.cursor()

    c.execute("SELECT id, nombre FROM maquinas")
    maquinas = c.fetchall()

    c.execute("""
        SELECT o.id, m.nombre, o.cantidad, o.estado, o.cerrado_en
        FROM ordenes o
        JOIN maquinas m ON m.id = o.maquina_id
        ORDER BY o.id DESC
    """)
    ordenes_sql = c.fetchall()

    ordenes = []

    for o in ordenes_sql:
        oid = o[0]

        c.execute("""
            SELECT SUM(cantidad_realizada), SUM(cantidad_total)
            FROM orden_actividades
            WHERE orden_id = %s
        """, (oid,))

        row_pct = c.fetchone()

        if row_pct and row_pct[1] and row_pct[1] > 0:
            porcentaje_general = round((row_pct[0] / row_pct[1]) * 100, 2)
        else:
            porcentaje_general = 0

        c.execute("""
            SELECT
                p.nombre,
                a.nombre,
                oa.cantidad_realizada,
                oa.cantidad_total
            FROM orden_actividades oa
            JOIN actividades a ON a.id = oa.actividad_id
            JOIN procesos p ON p.id = a.proceso_id
            WHERE oa.orden_id = %s
            ORDER BY p.id
        """, (oid,))
        acts = c.fetchall()

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
            "producto": o[1],
            "cantidad": o[2],
            "estado": o[3],
            "porcentaje": porcentaje_general,
            "cerrado_en": o[4],
            "procesos": [
                {"nombre": k, "actividades": v}
                for k, v in procesos.items()
            ]
        })

    conn.close()

    return templates.TemplateResponse("panel.html", {
        "request": request,
        "maquinas": maquinas,
        "ordenes": ordenes
    })


# ================= METRICAS OPERARIOS =================

@app.get("/metricas_operarios", response_class=HTMLResponse)
def metricas_operarios(request: Request):

    conn = db()
    c = conn.cursor()

    c.execute("""
    SELECT
        op.nombre,
        SUM(r.cantidad) as unidades,
        SUM(EXTRACT(EPOCH FROM (r.fin::timestamp - r.inicio::timestamp))) as segundos,
        COUNT(r.id) as operaciones
    FROM registros_produccion r
    JOIN operarios op ON op.id = r.operario_id
    GROUP BY op.nombre
    ORDER BY unidades DESC
    """)
    resumen = c.fetchall()

    resumen_final = []
    for nombre, unidades, segundos, operaciones in resumen:
        segundos = segundos or 0
        horas = round(segundos / 3600, 2) if segundos else 0
        productividad = round(unidades / horas, 2) if horas else 0
        resumen_final.append((nombre, unidades, horas, productividad, operaciones))

    c.execute("""
    SELECT op.nombre, a.nombre, r.cantidad, r.inicio, r.fin
    FROM registros_produccion r
    JOIN operarios op ON op.id = r.operario_id
    JOIN actividades a ON a.id = r.actividad_id
    ORDER BY r.id DESC
    """)
    detalle = c.fetchall()

    conn.close()

    return templates.TemplateResponse("Metricas.html", {
        "request": request,
        "resumen": resumen_final,
        "detalle": detalle
    })


# ================= KPI DASHBOARD =================

@app.get("/kpi", response_class=HTMLResponse)
def kpi(request: Request):

    if not require_admin(request):
        return RedirectResponse("/admin", 303)

    conn = db()
    c = conn.cursor()

    c.execute("""
    SELECT o.nombre, COALESCE(SUM(r.cantidad), 0)
    FROM registros_produccion r
    JOIN operarios o ON o.id = r.operario_id
    GROUP BY o.id, o.nombre
    """)
    por_operario = c.fetchall()

    c.execute("""
    SELECT o.nombre,
           COALESCE(SUM(EXTRACT(EPOCH FROM (r.fin::timestamp - r.inicio::timestamp)) / 60.0), 0)
    FROM registros_produccion r
    JOIN operarios o ON o.id = r.operario_id
    GROUP BY o.id, o.nombre
    """)
    minutos = c.fetchall()

    c.execute("""
    SELECT LEFT(inicio, 10), SUM(cantidad)
    FROM registros_produccion
    GROUP BY LEFT(inicio, 10)
    ORDER BY LEFT(inicio, 10)
    """)
    diario = c.fetchall()

    conn.close()

    return templates.TemplateResponse("kpi.html", {
        "request": request,
        "por_operario": por_operario,
        "minutos": minutos,
        "diario": diario
    })


# ================= CREAR ORDEN DESDE PANEL =================

@app.post("/crear_orden_web")
def crear_orden_web(cantidad: int = Form(...), maquina: int = Form(...)):

    conn = db()
    c = conn.cursor()

    c.execute("""
        INSERT INTO ordenes(maquina_id, cantidad, estado)
        VALUES (%s, %s, 'ABIERTA') RETURNING id
    """, (maquina, cantidad))

    orden_id = c.fetchone()[0]

    c.execute("""
        SELECT a.id
        FROM actividades a
        JOIN procesos p ON a.proceso_id = p.id
        WHERE p.maquina_id = %s
    """, (maquina,))
    acts = c.fetchall()

    for a in acts:
        c.execute("""
            INSERT INTO orden_actividades
            (orden_id, actividad_id, cantidad_total, cantidad_realizada)
            VALUES (%s, %s, %s, 0)
        """, (orden_id, a[0], cantidad))

    conn.commit()
    conn.close()

    return RedirectResponse("/panel", 303)


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
        (operario_id, orden_id, actividad_id, cantidad, inicio, fin, tiempo)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
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
        SET cantidad_realizada = cantidad_realizada + %s
        WHERE orden_id = %s AND actividad_id = %s
    """, (data["cantidad"], data["orden_id"], data["actividad_id"]))

    c.execute("""
        SELECT
            SUM(oa.cantidad_realizada),
            SUM(oa.cantidad_total)
        FROM orden_actividades oa
        JOIN actividades a ON a.id = oa.actividad_id
        WHERE oa.orden_id = %s
        AND a.nombre ILIKE '%Empaque%'
    """, (data["orden_id"],))

    row = c.fetchone()

    if row and row[1] and row[1] > 0:
        porcentaje = round((row[0] / row[1]) * 100, 2)
    else:
        porcentaje = 0

    c.execute("""
        UPDATE ordenes
        SET porcentaje = %s,
            estado = CASE WHEN %s >= 100 THEN 'CERRADA' ELSE estado END
        WHERE id = %s
    """, (porcentaje, porcentaje, data["orden_id"]))

    conn.commit()
    conn.close()

    return {"ok": True, "porcentaje": porcentaje}


# ================= EXPORTAR =================

@app.get("/exportar_excel")
def exportar_excel():

    conn = db()
    c = conn.cursor()

    c.execute("""
    SELECT o.nombre, a.nombre, r.cantidad, r.inicio, r.fin
    FROM registros_produccion r
    JOIN operarios o ON o.id = r.operario_id
    JOIN actividades a ON a.id = r.actividad_id
    """)
    rows = c.fetchall()

    wb = Workbook()
    ws = wb.active
    ws.append(["Operario", "Actividad", "Cantidad", "Inicio", "Fin"])
    for r in rows:
        ws.append(list(r))

    path = "/tmp/reporte_produccion.xlsx"
    wb.save(path)
    conn.close()

    return FileResponse(path, filename="reporte_produccion.xlsx")


# ================= ELIMINAR ORDEN =================

@app.get("/eliminar/{id}")
def eliminar(id: int):

    conn = db()
    c = conn.cursor()

    c.execute("DELETE FROM orden_actividades WHERE orden_id = %s", (id,))
    c.execute("DELETE FROM ordenes WHERE id = %s", (id,))

    conn.commit()
    conn.close()

    return RedirectResponse("/panel", 303)


# ================= CERRAR ORDEN =================

@app.get("/cerrar/{orden_id}")
def cerrar_orden(orden_id: int):

    conn = db()
    c = conn.cursor()

    c.execute("""
        UPDATE orden_actividades
        SET cantidad_realizada = cantidad_total
        WHERE orden_id = %s
    """, (orden_id,))

    c.execute("""
        UPDATE ordenes
        SET estado = 'CERRADA', cerrado_en = %s
        WHERE id = %s
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
    else:
        next_page = "/admin"

    if not next_page or next_page == "None":
        next_page = "/"

    return RedirectResponse(next_page, status_code=303)


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
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        data["operario_id"],
        data["orden_id"],
        data["actividad_id"],
        data["cantidad"],
        inicio.strftime("%Y-%m-%d %H:%M:%S"),
        fin.strftime("%Y-%m-%d %H:%M:%S"),
        tiempo
    ))

    c.execute("""
    UPDATE orden_actividades
    SET cantidad_realizada = cantidad_realizada + %s
    WHERE orden_id = %s AND actividad_id = %s
    """, (data["cantidad"], data["orden_id"], data["actividad_id"]))

    c.execute("""
        SELECT SUM(cantidad_realizada), SUM(cantidad_total)
        FROM orden_actividades
        WHERE orden_id = %s
    """, (data["orden_id"],))

    row = c.fetchone()

    if row and row[1] and row[1] > 0:
        porcentaje = round((row[0] / row[1]) * 100, 2)
    else:
        porcentaje = 0

    c.execute("""
        UPDATE ordenes
        SET porcentaje = %s,
            estado = CASE WHEN %s >= 100 THEN 'CERRADA' ELSE estado END
        WHERE id = %s
    """, (porcentaje, porcentaje, data["orden_id"]))

    conn.commit()
    conn.close()

    return {"status": "ok"}


# ================= IMPORTAR =================

@app.get("/importar")
def importar(request: Request):
    return templates.TemplateResponse("importar.html", {"request": request})


@app.get("/operarios")
def operarios():
    conn = db()
    c = conn.cursor()
    c.execute("SELECT id, nombre FROM operarios")
    rows = c.fetchall()
    conn.close()
    return rows


@app.get("/maquinas")
def maquinas():
    conn = db()
    c = conn.cursor()
    c.execute("SELECT id, nombre FROM maquinas")
    rows = c.fetchall()
    conn.close()
    return rows


@app.get("/ordenes")
def ordenes_android():
    conn = db()
    c = conn.cursor()
    c.execute("""
    SELECT id, maquina_id, estado, porcentaje
    FROM ordenes
    WHERE estado != 'CERRADA'
    """)
    rows = c.fetchall()
    conn.close()
    return rows


@app.get("/procesos/{orden_id}")
def procesos_android(orden_id: int):
    conn = db()
    c = conn.cursor()
    c.execute("""
    SELECT DISTINCT p.id, p.nombre
    FROM orden_actividades oa
    JOIN actividades a ON a.id = oa.actividad_id
    JOIN procesos p ON p.id = a.proceso_id
    WHERE oa.orden_id = %s
    """, (orden_id,))
    rows = c.fetchall()
    conn.close()
    return rows


@app.get("/actividades/{orden}/{proceso}")
def actividades_android(orden: int, proceso: int):
    conn = db()
    c = conn.cursor()
    c.execute("""
    SELECT a.id, a.nombre
    FROM orden_actividades oa
    JOIN actividades a ON a.id = oa.actividad_id
    WHERE oa.orden_id = %s AND a.proceso_id = %s
    """, (orden, proceso))
    rows = c.fetchall()
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
def metricas(request: Request):

    conn = db()
    c = conn.cursor()

    c.execute("""
    SELECT o.nombre,
           SUM(r.cantidad) as unidades,
           SUM(EXTRACT(EPOCH FROM (r.fin::timestamp - r.inicio::timestamp)) / 60.0) as minutos
    FROM registros_produccion r
    JOIN operarios o ON o.id = r.operario_id
    GROUP BY o.nombre
    ORDER BY unidades DESC
    """)
    resumen = c.fetchall()

    c.execute("""
    SELECT o.nombre, a.nombre, r.cantidad, r.inicio, r.fin
    FROM registros_produccion r
    JOIN operarios o ON o.id = r.operario_id
    JOIN actividades a ON a.id = r.actividad_id
    ORDER BY r.id DESC
    """)
    detalle = c.fetchall()

    conn.close()

    return templates.TemplateResponse("Metricas.html", {
        "request": request,
        "resumen": resumen,
        "detalle": detalle
    })


# ================= IMPORTAR EXCEL =================

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

    for _, row in df_maquinas.iterrows():
        c.execute("INSERT INTO maquinas(nombre) VALUES(%s)", (row["nombre"],))

    for _, row in df_procesos.iterrows():
        c.execute("SELECT id FROM maquinas WHERE nombre = %s", (row["maquina"],))
        mid = c.fetchone()
        if mid:
            c.execute("INSERT INTO procesos(maquina_id, nombre) VALUES(%s, %s)", (mid[0], row["nombre"]))

    for _, row in df_actividades.iterrows():
        c.execute("SELECT id FROM procesos WHERE nombre = %s", (row["proceso"],))
        pid = c.fetchone()
        if pid:
            c.execute("INSERT INTO actividades(proceso_id, nombre) VALUES(%s, %s)", (pid[0], row["nombre"]))

    for _, row in df_operarios.iterrows():
        c.execute("INSERT INTO operarios(nombre) VALUES(%s)", (row["nombre"],))

    conn.commit()
    conn.close()

    return RedirectResponse("/", 303)


# ================= RESETEAR BASE =================

@app.get("/resetear_base")
def resetear_base():

    conn = db()
    c = conn.cursor()

    c.execute("DELETE FROM registros_produccion")
    c.execute("DELETE FROM actividades")
    c.execute("DELETE FROM procesos")
    c.execute("DELETE FROM maquinas")
    c.execute("DELETE FROM operarios")

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

    return RedirectResponse("/", 303)


@app.get("/borrar_registros")
def borrar_registros():

    conn = db()
    c = conn.cursor()
    c.execute("DELETE FROM registros_produccion")
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/limpiar_excel")
def limpiar_excel(request: Request):

    if not require_admin(request):
        return RedirectResponse("/admin", 303)

    conn = db()
    c = conn.cursor()

    c.execute("DELETE FROM registros_produccion")
    c.execute("DELETE FROM orden_actividades")
    c.execute("DELETE FROM ordenes")
    c.execute("DELETE FROM actividades")
    c.execute("DELETE FROM procesos")
    c.execute("DELETE FROM maquinas")
    c.execute("DELETE FROM operarios")

    conn.commit()
    conn.close()

    return RedirectResponse("/", 303)


@app.get("/ver_actividades")
def ver_actividades():
    conn = db()
    c = conn.cursor()
    c.execute("SELECT id, nombre FROM actividades")
    rows = c.fetchall()
    conn.close()
    return rows


@app.get("/ver_bonos")
def ver_bonos():
    conn = db()
    c = conn.cursor()
    c.execute("""
    SELECT o.nombre, a.nombre, b.unidades, b.horas, b.rendimiento, b.porcentaje, b.valor
    FROM bonos b
    JOIN operarios o ON o.id = b.operario_id
    JOIN actividades a ON a.id = b.actividad_id
    """)
    rows = c.fetchall()
    conn.close()
    return rows


@app.get("/ver_registros")
def ver_registros():
    conn = db()
    c = conn.cursor()
    c.execute("SELECT * FROM registros_produccion")
    rows = c.fetchall()
    conn.close()
    return rows


META_MENSUAL = 5000
TARIFA_HH = 10000


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
            VALUES (%s, %s, %s, 0)
        """, (actividad_id, unidades, costo))

    conn.commit()
    conn.close()

    return {"estandares_cargados": len(df)}


@app.get("/bonos", response_class=HTMLResponse)
def bonos(request: Request):

    if not require_admin(request):
        return RedirectResponse("/admin", 303)

    hoy = datetime.now()
    mes = int(request.query_params.get("mes", hoy.month))
    anio = int(request.query_params.get("anio", hoy.year))

    from routers.bonos import bonos_mes
    datos = bonos_mes(mes, anio)

    return templates.TemplateResponse("bonos.html", {
        "request": request,
        "datos": datos,
        "mes": mes,
        "anio": anio
    })


@app.get("/bonos/detalle", response_class=HTMLResponse)
def detalle_bono(request: Request):

    if not require_admin(request):
        return RedirectResponse("/admin", 303)

    nombre = request.query_params.get("nombre")
    mes = int(request.query_params.get("mes"))
    anio = int(request.query_params.get("anio"))

    conn = db()
    c = conn.cursor()

    c.execute("""
        SELECT
            a.id,
            a.nombre,
            SUM(r.cantidad) as unidades,
            SUM(EXTRACT(EPOCH FROM (r.fin::timestamp - r.inicio::timestamp)) / 3600.0) as horas
        FROM registros_produccion r
        JOIN operarios o ON o.id = r.operario_id
        JOIN actividades a ON a.id = r.actividad_id
        WHERE o.nombre = %s
        AND TO_CHAR(r.inicio::timestamp, 'MM') = %s
        AND TO_CHAR(r.inicio::timestamp, 'YYYY') = %s
        GROUP BY a.id, a.nombre
    """, (nombre, f"{mes:02d}", str(anio)))
    rows = c.fetchall()

    detalle = []
    total_bono = 0

    for actividad_id, actividad, unidades, horas in rows:

        horas = horas or 0
        unidades = unidades or 0
        rendimiento_real = (unidades / horas) if horas > 0 else 0

        c.execute("""
            SELECT unidades_por_hora, costo_mo_unidad
            FROM estandares_actividad
            WHERE actividad_id = %s
        """, (actividad_id,))
        est = c.fetchone()

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
            "horas": round(horas, 2),
            "rendimiento": round(rendimiento_real, 2),
            "estandar": unidades_estandar,
            "eficiencia": round(eficiencia * 100, 2),
            "porcentaje": porcentaje * 100,
            "bono": round(bono, 2)
        })

    conn.close()

    return templates.TemplateResponse("bono_detalle.html", {
        "request": request,
        "nombre": nombre,
        "mes": mes,
        "anio": anio,
        "detalle": detalle,
        "total_bono": round(total_bono, 2)
    })


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
            "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
            (username, hashed, role)
        )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()

    return RedirectResponse("/usuarios", status_code=303)


@app.get("/usuarios/eliminar/{user_id}")
def eliminar_usuario(request: Request, user_id: int):

    if not require_admin(request):
        return RedirectResponse("/admin", status_code=303)

    conn = db()
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id = %s", (user_id,))
    conn.commit()
    conn.close()

    return RedirectResponse("/usuarios", status_code=303)


@app.get("/api/kardex/{referencia}")
def api_kardex(referencia: str):

    conn = db()
    c = conn.cursor()

    c.execute("""
        SELECT fecha, tipo, cantidad, saldo
        FROM kardex
        WHERE referencia = %s
        ORDER BY fecha DESC
    """, (referencia,))
    data = c.fetchall()
    conn.close()

    return [
        {"fecha": r[0], "tipo": r[1], "cantidad": r[2], "saldo": r[3]}
        for r in data
    ]
