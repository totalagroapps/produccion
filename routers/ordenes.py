from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
from database import db
from auth import require_admin

router = APIRouter()
templates = Jinja2Templates(directory="templates")


# ================= PANEL =================

@router.get("/panel", response_class=HTMLResponse)
def panel(request: Request):

    if not require_admin(request):
        return RedirectResponse("/admin", 303)

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

        c.execute("""
            SELECT SUM(cantidad_realizada),
                   SUM(cantidad_total)
            FROM orden_actividades
            WHERE orden_id=%s
        """,(oid,))

        row_pct = c.fetchone()

        if row_pct and row_pct[1] and row_pct[1] > 0:
            porcentaje_general = round((row_pct[0] / row_pct[1]) * 100, 2)
        else:
            porcentaje_general = 0

        ordenes.append({
            "id": o[0],
            "producto": o[1],
            "cantidad": o[2],
            "estado": o[3],
            "porcentaje": porcentaje_general,
            "cerrado_en": o[4]
        })

    conn.close()

    return templates.TemplateResponse(
        request=request, name="panel.html", context={
        "request":request,
        "maquinas":maquinas,
        "ordenes":ordenes
    })


# ================= CREAR ORDEN =================

@router.post("/crear_orden_web")
def crear_orden_web(cantidad: int = Form(...), maquina: int = Form(...)):

    conn = db()
    c = conn.cursor()

    c.execute("""
        INSERT INTO ordenes(maquina_id,cantidad,estado)
        VALUES(%s,%s, 'ABIERTA') RETURNING id
    """,(maquina,cantidad))

    orden_id = c.fetchone()[0]

    c.execute("""
        SELECT a.id
        FROM actividades a
        JOIN procesos p ON a.proceso_id = p.id
        WHERE p.maquina_id = %s
    """,(maquina,))

    acts = c.fetchall()

    for a in acts:
        c.execute("""
            INSERT INTO orden_actividades
            (orden_id,actividad_id,cantidad_total,cantidad_realizada)
            VALUES(%s,%s,%s,0)
        """,(orden_id,a[0],cantidad))

    conn.commit()
    conn.close()
    
# ================= CERRAR ORDEN =================

@router.get("/cerrar/{orden_id}")
def cerrar_orden(orden_id: int, request: Request):

    if not require_admin(request):
        return RedirectResponse("/admin", 303)

    conn = db()
    c = conn.cursor()

    c.execute("""
        UPDATE orden_actividades
        SET cantidad_realizada = cantidad_total
        WHERE orden_id=%s
    """, (orden_id,))

    c.execute("""
        UPDATE ordenes
        SET estado='CERRADA',
            cerrado_en=%s
        WHERE id=%s
    """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), orden_id))

    # obtener maquina y cantidad de la orden
    c.execute("""
    SELECT maquina_id, cantidad
    FROM ordenes
    WHERE id=%s
    """,(orden_id,))

    orden = c.fetchone()

    maquina_id = orden[0]
    cantidad = orden[1]

    # obtener nombre del producto
    c.execute("""
    SELECT nombre
    FROM maquinas
    WHERE id=%s
    """,(maquina_id,))

    producto = c.fetchone()[0]