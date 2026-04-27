from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from database import db
from datetime import datetime

router = APIRouter()


# ================= FUNCION CALCULO BONOS =================

def bonos_mes(mes: int, anio: int):

    conn = db()
    c = conn.cursor()

    rows = c.execute("""
        SELECT
            o.id,
            o.nombre,
            SUM(r.cantidad) as unidades,
            SUM((EXTRACT(EPOCH FROM r.fin::timestamp) - EXTRACT(EPOCH FROM r.inicio::timestamp)) / 3600.0) as horas,
            COUNT(DISTINCT date(r.inicio)) as dias_trabajados
        FROM registros_produccion r
        JOIN operarios o ON o.id = r.operario_id
        WHERE TO_CHAR(r.inicio::timestamp, 'MM') = %s
        AND TO_CHAR(r.inicio::timestamp, 'YYYY') = %s
        GROUP BY o.id, o.nombre
    """, (f"{mes:02d}", str(anio))).fetchall()

    resultado = []

    for operario_id, nombre, unidades, horas, dias in rows:

        horas = horas or 0
        unidades = unidades or 0
        dias = dias or 0

        if horas <= 0:
            continue

        horas_disponibles = (dias * 530) / 60
        eficiencia_ocupacion = horas / horas_disponibles if horas_disponibles > 0 else 0

        est = c.execute("""
            SELECT AVG(e.unidades_por_hora),
                   AVG(e.costo_mo_unidad)
            FROM registros_produccion r
            JOIN estandares_actividad e ON e.actividad_id = r.actividad_id
            WHERE r.operario_id = %s
            AND TO_CHAR(r.inicio::timestamp, 'MM') = %s
            AND TO_CHAR(r.inicio::timestamp, 'YYYY') = %s
        """, (operario_id, f"{mes:02d}", str(anio))).fetchone()

        if not est or not est[0]:
            continue

        unidades_estandar = est[0]
        costo_base = est[1] or 0

        rendimiento_real = unidades / horas
        eficiencia_productiva = rendimiento_real / unidades_estandar if unidades_estandar else 0

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


# ================= PAGINA BONOS =================

@router.get("/bonos", response_class=HTMLResponse)
def bonos(request: Request):

    if not request.session.get("role") == "admin":
        return RedirectResponse("/admin", 303)

    hoy = datetime.now()

    mes = int(request.query_params.get("mes", hoy.month))
    anio = int(request.query_params.get("anio", hoy.year))

    datos = bonos_mes(mes, anio)

    return request.app.state.templates.TemplateResponse(
        request=request, name="bonos.html", context={
            "request": request,
            "datos": datos,
            "mes": mes,
            "anio": anio
        }
    )


# ================= DETALLE BONO =================

@router.get("/bonos/detalle", response_class=HTMLResponse)
def detalle_bono(request: Request):

    if not request.session.get("role") == "admin":
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
            SUM((EXTRACT(EPOCH FROM r.fin::timestamp) - EXTRACT(EPOCH FROM r.inicio::timestamp)) / 3600.0) as horas
        FROM registros_produccion r
        JOIN operarios o ON o.id = r.operario_id
        JOIN actividades a ON a.id = r.actividad_id
        WHERE o.nombre = %s
        AND TO_CHAR(r.inicio::timestamp, 'MM') = %s
        AND TO_CHAR(r.inicio::timestamp, 'YYYY') = %s
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
            WHERE actividad_id = %s
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

    return request.app.state.templates.TemplateResponse(
        request=request, name="bono_detalle.html", context={
            "request": request,
            "nombre": nombre,
            "mes": mes,
            "anio": anio,
            "detalle": detalle,
            "total_bono": round(total_bono,2)
        }
    )