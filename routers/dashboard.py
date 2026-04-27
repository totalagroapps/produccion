from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from database import db

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home(request: Request):

    # 🔐 Protección
    if not request.session.get("role") == "admin":
        return RedirectResponse("/admin", 303)

    conn = db()
    c = conn.cursor()

    # Órdenes activas
    ordenes_activas = c.execute("""
        SELECT COUNT(*)
        FROM ordenes
        WHERE estado='ABIERTA'
    """).fetchone()[0]

    # Producción hoy
    produccion_hoy = c.execute("""
        SELECT IFNULL(SUM(cantidad),0)
        FROM registros_produccion
        WHERE date(inicio)=date('now')
    """).fetchone()[0]

    # Operarios activos hoy
    operarios_activos = c.execute("""
        SELECT COUNT(DISTINCT operario_id)
        FROM registros_produccion
        WHERE date(inicio)=date('now')
    """).fetchone()[0]

    # Avance promedio general
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

    return request.app.state.templates.TemplateResponse(
        request=request, name="home.html", context={
            "request": request,
            "ordenes_activas": ordenes_activas,
            "produccion_hoy": produccion_hoy,
            "avance_promedio": avance_promedio,
            "operarios_activos": operarios_activos
        }
    )