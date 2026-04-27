from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from database import db

router = APIRouter()

# ================= METRICAS OPERARIOS =================

@router.get("/metricas_operarios", response_class=HTMLResponse)
def metricas_operarios(request: Request):

    if not request.session.get("role") == "admin":
        return RedirectResponse("/admin", 303)

    conn = db()
    c = conn.cursor()

    # ===== RESUMEN AGRUPADO =====
    c.execute("""
    SELECT 
        op.nombre,
        SUM(r.cantidad) as unidades,
        SUM(EXTRACT(EPOCH FROM r.fin::timestamp)-EXTRACT(EPOCH FROM r.inicio::timestamp)) as segundos,
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

        resumen_final.append(
            (nombre, unidades, horas, productividad, operaciones)
        )

    # ===== DETALLE =====
    c.execute("""
        SELECT op.nombre,
            a.nombre,
            r.cantidad,
            r.inicio,
            r.fin
        FROM registros_produccion r
        JOIN operarios op ON op.id=r.operario_id
        JOIN actividades a ON a.id=r.actividad_id
        ORDER BY r.id DESC
    """)

    detalle = c.fetchall()

    conn.close()

    return request.app.state.templates.TemplateResponse(
        request=request, name="Metricas.html", context={
            "request": request,
            "resumen": resumen_final,
            "detalle": detalle
        }
    )


# ================= METRICAS SIMPLE =================

@router.get("/metricas", response_class=HTMLResponse)
def metricas(request: Request):

    if not request.session.get("role") == "admin":
        return RedirectResponse("/admin", 303)

    conn = db()
    c = conn.cursor()

    # 🔧 resumen (ya estaba bien)
    c.execute("""
        SELECT o.nombre,
            SUM(r.cantidad) as unidades,
            SUM((EXTRACT(EPOCH FROM r.fin::timestamp)-EXTRACT(EPOCH FROM r.inicio::timestamp))/60.0) as minutos
        FROM registros_produccion r
        JOIN operarios o ON o.id=r.operario_id
        GROUP BY o.nombre
        ORDER BY unidades DESC
    """)
    resumen = c.fetchall()

    # 🔧 detalle (corregido)
    c.execute("""
    SELECT o.nombre,
           a.nombre,
           r.cantidad,
           r.inicio,
           r.fin
    FROM registros_produccion r
    JOIN operarios o ON o.id=r.operario_id
    JOIN actividades a ON a.id=r.actividad_id
    ORDER BY r.id DESC
    """)
    detalle = c.fetchall()

    conn.close()

    return request.app.state.templates.TemplateResponse(
        request=request, name="Metricas.html", context={
            "request": request,
            "resumen": resumen,
            "detalle": detalle
        }
    )


# ================= KPI DASHBOARD =================

@router.get("/kpi", response_class=HTMLResponse)
def kpi(request: Request):

    if not request.session.get("role") == "admin":
        return RedirectResponse("/admin", 303)

    conn = db()
    c = conn.cursor()

    # KPI 1: piezas por operario
    c.execute("""
    SELECT o.nombre,
           COALESCE(SUM(r.cantidad),0)
    FROM registros_produccion r
    JOIN operarios o ON o.id=r.operario_id
    GROUP BY o.id
    """)
    por_operario = c.fetchall()

    # KPI 2: minutos trabajados
    c.execute("""
    SELECT o.nombre,
           COALESCE(SUM(EXTRACT(EPOCH FROM (r.fin::timestamp - r.inicio::timestamp)) / 60.0), 0)
    FROM registros_produccion r
    JOIN operarios o ON o.id=r.operario_id
    GROUP BY o.id
    """)
    minutos = c.fetchall()

    # KPI 3: producción diaria
    c.execute("""
    SELECT substr(inicio,1,10),
           SUM(cantidad)
    FROM registros_produccion
    GROUP BY substr(inicio,1,10)
    ORDER BY substr(inicio,1,10)
    """)
    diario = c.fetchall()

    conn.close()

    return request.app.state.templates.TemplateResponse(
        request=request, name="kpi.html", context={
            "request": request,
            "por_operario": por_operario,
            "minutos": minutos,
            "diario": diario
        }
    )