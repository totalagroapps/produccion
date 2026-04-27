from fastapi import APIRouter
from datetime import datetime, timedelta
from database import db

router = APIRouter()


# ================= REGISTRO ANDROID =================

@router.post("/registro_android")
def registro_android(data: dict):

    conn = db()
    c = conn.cursor()

    ahora = datetime.now()
    tiempo = int(data.get("tiempo", 0))

    inicio = ahora
    fin = ahora + timedelta(seconds=tiempo)

    c.execute("""
    INSERT INTO registros_produccion
    (operario_id, orden_id, actividad_id, cantidad, inicio, fin, tiempo)
    VALUES (%s,%s,%s,%s,%s,%s,%s)
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
    SET cantidad_realizada = cantidad_realizada + %s
    WHERE orden_id=%s AND actividad_id=%s
    """,(
        data["cantidad"],
        data["orden_id"],
        data["actividad_id"]
    ))

    # recalcular porcentaje general
    c.execute("""
        SELECT SUM(cantidad_realizada),
               SUM(cantidad_total)
        FROM orden_actividades
        WHERE orden_id=%s
    """,(data["orden_id"],))

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
    """,(porcentaje, porcentaje, data["orden_id"]))

    conn.commit()
    conn.close()

    return {"status":"ok"}


# ================= LISTAS PARA ANDROID =================

@router.get("/operarios")
def operarios():
    conn = db()
    c = conn.cursor()
    rows = c.execute("SELECT id,nombre FROM operarios").fetchall()
    conn.close()
    return rows


@router.get("/maquinas")
def maquinas():
    conn = db()
    c = conn.cursor()
    rows = c.execute("SELECT id,nombre FROM maquinas").fetchall()
    conn.close()
    return rows


@router.get("/ordenes")
def ordenes_android():
    conn = db()
    c = conn.cursor()
    rows = c.execute("""
    SELECT id,maquina_id,estado,porcentaje
    FROM ordenes
    WHERE estado!='CERRADA'
    """).fetchall()
    conn.close()
    return rows


@router.get("/procesos/{orden_id}")
def procesos_android(orden_id:int):
    conn = db()
    c = conn.cursor()
    rows = c.execute("""
    SELECT DISTINCT p.id,p.nombre
    FROM orden_actividades oa
    JOIN actividades a ON a.id=oa.actividad_id
    JOIN procesos p ON p.id=a.proceso_id
    WHERE oa.orden_id=%s
    """,(orden_id,)).fetchall()
    conn.close()
    return rows


@router.get("/actividades/{orden}/{proceso}")
def actividades_android(orden:int, proceso:int):
    conn = db()
    c = conn.cursor()
    rows = c.execute("""
    SELECT a.id,a.nombre
    FROM orden_actividades oa
    JOIN actividades a ON a.id=oa.actividad_id
    WHERE oa.orden_id=%s AND a.proceso_id=%s
    """,(orden,proceso)).fetchall()
    conn.close()
    return rows