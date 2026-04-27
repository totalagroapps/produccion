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

    # 🔧 maquinas
    c.execute("SELECT id,nombre FROM maquinas")
    maquinas = c.fetchall()

    # 🔧 ordenes
    c.execute("""
        SELECT o.id,
               m.nombre,
               o.cantidad,
               o.estado,
               o.cerrado_en
        FROM ordenes o
        JOIN maquinas m ON m.id=o.maquina_id
        ORDER BY o.id DESC
    """)
    ordenes_sql = c.fetchall()

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