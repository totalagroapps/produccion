from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta
from database import db

router = APIRouter()


def campo_entero(data: dict, *nombres: str) -> int:
    for nombre in nombres:
        valor = data.get(nombre)
        if valor is not None and valor != "":
            return int(valor)

    raise HTTPException(
        status_code=400,
        detail=f"Campo requerido faltante: {'/'.join(nombres)}"
    )


def fecha_android(valor):
    if not valor:
        return None

    texto = str(valor).replace("Z", "+00:00")

    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        return datetime.strptime(str(valor), "%Y-%m-%d %H:%M:%S")


# ================= REGISTRO ANDROID =================

@router.post("/registro_android")
def registro_android(data: dict):

    try:
        operario_id = campo_entero(data, "operario_id", "operario")
        orden_id = campo_entero(data, "orden_id", "orden")
        actividad_id = campo_entero(data, "actividad_id", "actividad")
        cantidad = campo_entero(data, "cantidad")
        tiempo = int(data.get("tiempo") or 0)
    except ValueError:
        raise HTTPException(status_code=400, detail="Campos numericos invalidos")

    conn = db()
    c = conn.cursor()

    inicio = fecha_android(data.get("inicio"))
    fin = fecha_android(data.get("fin"))

    if inicio and fin:
        tiempo = max(0, int((fin - inicio).total_seconds()))
    else:
        fin = datetime.now()
        inicio = fin - timedelta(seconds=tiempo)

    c.execute("""
    INSERT INTO registros_produccion
    (operario_id, orden_id, actividad_id, cantidad, inicio, fin, tiempo)
    VALUES (%s,%s,%s,%s,%s,%s,%s)
    """,(
        operario_id,
        orden_id,
        actividad_id,
        cantidad,
        inicio.strftime("%Y-%m-%d %H:%M:%S"),
        fin.strftime("%Y-%m-%d %H:%M:%S"),
        tiempo
    ))

    # actualizar actividad
    c.execute("""
    UPDATE orden_actividades
    SET cantidad_realizada = cantidad_realizada + %s
    WHERE orden_id=%s AND actividad_id=%s
    """,(
        cantidad,
        orden_id,
        actividad_id
    ))

    # recalcular porcentaje general
    c.execute("""
        SELECT SUM(cantidad_realizada),
               SUM(cantidad_total)
        FROM orden_actividades
        WHERE orden_id=%s
    """,(orden_id,))

    row = c.fetchone()

    if row and row[1] and row[1] > 0:
        porcentaje = round((row[0] / row[1]) * 100, 2)
    else:
        porcentaje = 0

    c.execute("""
        UPDATE ordenes
        SET porcentaje=%s,
            estado=CASE WHEN %s >= 100 THEN 'CERRADA' ELSE estado END
        WHERE id=%s
    """,(porcentaje, porcentaje, orden_id))

    conn.commit()
    conn.close()

    return {"status":"ok"}


# ================= LISTAS PARA ANDROID =================

@router.get("/operarios")
def operarios():
    conn = db()
    c = conn.cursor()

    c.execute("SELECT id,nombre FROM operarios")
    rows = c.fetchall() or []

    conn.close()

    return [{"id": r[0], "nombre": r[1]} for r in rows]


@router.get("/maquinas")
def maquinas():
    conn = db()
    c = conn.cursor()

    c.execute("SELECT id,nombre FROM maquinas")
    rows = c.fetchall() or []

    conn.close()

    return [{"id": r[0], "nombre": r[1]} for r in rows]


@router.get("/ordenes")
def ordenes_android():
    conn = db()
    c = conn.cursor()

    c.execute("""
    SELECT id,maquina_id,estado,porcentaje
    FROM ordenes
    WHERE estado!='CERRADA'
    """)
    rows = c.fetchall() or []

    conn.close()

    return [
        {
            "id": r[0],
            "maquina_id": r[1],
            "estado": r[2],
            "porcentaje": r[3]
        }
        for r in rows
    ]


@router.get("/procesos/{orden_id}")
def procesos_android(orden_id:int):
    conn = db()
    c = conn.cursor()

    c.execute("""
    SELECT DISTINCT p.id,p.nombre
    FROM orden_actividades oa
    JOIN actividades a ON a.id=oa.actividad_id
    JOIN procesos p ON p.id=a.proceso_id
    WHERE oa.orden_id=%s
    """,(orden_id,))
    rows = c.fetchall() or []

    conn.close()

    return [{"id": r[0], "nombre": r[1]} for r in rows]


@router.get("/actividades/{orden}/{proceso}")
def actividades_android(orden:int, proceso:int):
    conn = db()
    c = conn.cursor()

    c.execute("""
    SELECT a.id,a.nombre
    FROM orden_actividades oa
    JOIN actividades a ON a.id=oa.actividad_id
    WHERE oa.orden_id=%s AND a.proceso_id=%s
    """,(orden,proceso))
    rows = c.fetchall() or []

    conn.close()

    return [{"id": r[0], "nombre": r[1]} for r in rows]
