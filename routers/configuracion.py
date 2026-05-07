from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from psycopg2 import sql
from database import db

router = APIRouter()

# Solo tablas maestras. Las tablas operativas no se editan desde este panel
# porque dependen de estos IDs para ordenes, registros y bonos.
TABLAS_PERMITIDAS = [
    "maquinas",
    "procesos",
    "actividades",
    "operarios",
    "estandares_actividad",
]

REFERENCIAS = {
    "maquinas": [("procesos", "maquina_id"), ("ordenes", "maquina_id")],
    "procesos": [("actividades", "proceso_id")],
    "actividades": [
        ("orden_actividades", "actividad_id"),
        ("registros_produccion", "actividad_id"),
        ("bonos", "actividad_id"),
        ("estandares_actividad", "actividad_id"),
    ],
    "operarios": [("registros_produccion", "operario_id"), ("bonos", "operario_id")],
    "estandares_actividad": [],
}


def validar_tabla(tabla: str):
    if tabla not in TABLAS_PERMITIDAS:
        raise HTTPException(status_code=400, detail="Tabla no permitida")


def limpiar_valor(valor):
    if valor == "":
        return None
    return valor


def sincronizar_secuencia(cursor, tabla: str):
    cursor.execute("SELECT pg_get_serial_sequence(%s, 'id')", (tabla,))
    seq = cursor.fetchone()[0]
    if not seq:
        return

    cursor.execute(
        sql.SQL("SELECT COALESCE(MAX(id), 0) FROM {}").format(sql.Identifier(tabla))
    )
    max_id = cursor.fetchone()[0] or 0

    if max_id > 0:
        cursor.execute("SELECT setval(%s, %s, true)", (seq, max_id))
    else:
        cursor.execute("SELECT setval(%s, 1, false)", (seq,))


def fila_en_uso(cursor, tabla: str, id: int):
    for tabla_ref, columna_ref in REFERENCIAS.get(tabla, []):
        cursor.execute(
            sql.SQL("SELECT COUNT(*) FROM {} WHERE {} = %s").format(
                sql.Identifier(tabla_ref), sql.Identifier(columna_ref)
            ),
            (id,),
        )
        total = cursor.fetchone()[0] or 0
        if total > 0:
            return tabla_ref, columna_ref, total
    return None



def texto_obligatorio(data: dict, campo: str, etiqueta: str):
    valor = str(data.get(campo, "")).strip()
    if not valor:
        raise HTTPException(status_code=400, detail=f"{etiqueta} es obligatorio")
    return valor


def entero_obligatorio(data: dict, campo: str, etiqueta: str):
    try:
        valor = int(str(data.get(campo, "")).strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{etiqueta} invalido") from exc
    if valor <= 0:
        raise HTTPException(status_code=400, detail=f"{etiqueta} invalido")
    return valor


def float_obligatorio(data: dict, campo: str, etiqueta: str):
    try:
        valor = float(str(data.get(campo, "")).strip().replace(",", "."))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{etiqueta} invalido") from exc
    if valor <= 0:
        raise HTTPException(status_code=400, detail=f"{etiqueta} debe ser mayor a 0")
    return valor


def float_opcional(data: dict, campo: str):
    valor = data.get(campo, "")
    if valor is None or str(valor).strip() == "":
        return 0
    try:
        return float(str(valor).strip().replace(",", "."))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{campo} invalido") from exc


def crear_estandar(cursor, actividad_id: int, data: dict):
    unidades = float_obligatorio(data, "unidades_por_hora", "Unidades por hora")
    costo_unidad = float_opcional(data, "costo_mo_unidad")
    costo_hora = float_opcional(data, "costo_mo_hora")

    sincronizar_secuencia(cursor, "estandares_actividad")
    cursor.execute(
        """
        INSERT INTO estandares_actividad
            (actividad_id, unidades_por_hora, costo_mo_unidad, costo_mo_hora)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (actividad_id, unidades, costo_unidad, costo_hora),
    )
    estandar_id = cursor.fetchone()[0]
    sincronizar_secuencia(cursor, "estandares_actividad")
    return estandar_id


def sincronizar_actividad_en_ordenes_abiertas(cursor, actividad_id: int):
    cursor.execute(
        """
        INSERT INTO orden_actividades
            (orden_id, actividad_id, cantidad_total, cantidad_realizada)
        SELECT
            o.id,
            a.id,
            o.cantidad,
            0
        FROM actividades a
        JOIN procesos p ON p.id = a.proceso_id
        JOIN ordenes o ON o.maquina_id = p.maquina_id
        WHERE a.id = %s
        AND o.estado != 'CERRADA'
        AND NOT EXISTS (
            SELECT 1
            FROM orden_actividades oa
            WHERE oa.orden_id = o.id
            AND oa.actividad_id = a.id
        )
        """,
        (actividad_id,),
    )
    return cursor.rowcount or 0


def guardar_filas(tabla: str, columnas: list, filas: list):
    validar_tabla(tabla)

    if not columnas or columnas[0] != "id":
        raise HTTPException(status_code=400, detail="La primera columna debe ser id")

    columnas_editables = columnas[1:]
    conn = db()
    c = conn.cursor()

    try:
        sincronizar_secuencia(c, tabla)

        for fila in filas:
            if len(fila) != len(columnas):
                raise HTTPException(status_code=400, detail="Fila con numero de columnas invalido")

            id_raw = str(fila[0]).strip() if fila[0] is not None else ""
            valores = [limpiar_valor(v) for v in fila[1:]]

            if not id_raw and all(v is None for v in valores):
                continue

            if id_raw:
                try:
                    row_id = int(id_raw)
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail="ID invalido") from exc

                asignaciones = [
                    sql.SQL("{} = %s").format(sql.Identifier(col))
                    for col in columnas_editables
                ]
                query = sql.SQL("UPDATE {} SET {} WHERE id = %s").format(
                    sql.Identifier(tabla), sql.SQL(", ").join(asignaciones)
                )
                c.execute(query, valores + [row_id])
            else:
                query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                    sql.Identifier(tabla),
                    sql.SQL(", ").join(sql.Identifier(col) for col in columnas_editables),
                    sql.SQL(", ").join(sql.Placeholder() for _ in columnas_editables),
                )
                c.execute(query, valores)

        sincronizar_secuencia(c, tabla)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {"ok": True}


@router.get("/config/tablas")
def ver_tablas():
    return [(tabla,) for tabla in TABLAS_PERMITIDAS]


@router.get("/config/tablas_lista")
def tablas_lista():
    return TABLAS_PERMITIDAS


@router.get("/config/catalogos")
def catalogos_configuracion():
    conn = db()
    c = conn.cursor()
    c.execute("SELECT id, nombre FROM maquinas ORDER BY nombre, id")
    maquinas = [{"id": row[0], "nombre": row[1]} for row in c.fetchall()]

    c.execute("""
        SELECT p.id, p.nombre, p.maquina_id, m.nombre
        FROM procesos p
        JOIN maquinas m ON m.id = p.maquina_id
        ORDER BY m.nombre, p.nombre, p.id
    """)
    procesos = [
        {
            "id": row[0],
            "nombre": row[1],
            "maquina_id": row[2],
            "maquina": row[3],
        }
        for row in c.fetchall()
    ]
    conn.close()
    return {"maquinas": maquinas, "procesos": procesos}


@router.post("/config/asistente/proceso")
def crear_proceso_asistente(data: dict):
    maquina_id = entero_obligatorio(data, "maquina_id", "Maquina")
    nombre = texto_obligatorio(data, "nombre", "Nombre del proceso")
    actividad_nombre = str(data.get("actividad_nombre", "")).strip()

    conn = db()
    c = conn.cursor()
    try:
        c.execute("SELECT id FROM maquinas WHERE id = %s", (maquina_id,))
        if not c.fetchone():
            raise HTTPException(status_code=400, detail="La maquina seleccionada no existe")

        c.execute(
            """
            SELECT id
            FROM procesos
            WHERE maquina_id = %s
            AND lower(trim(nombre)) = lower(trim(%s))
            """,
            (maquina_id, nombre),
        )
        if c.fetchone():
            raise HTTPException(status_code=400, detail="Ese proceso ya existe para esta maquina")

        sincronizar_secuencia(c, "procesos")
        c.execute(
            "INSERT INTO procesos (maquina_id, nombre) VALUES (%s, %s) RETURNING id",
            (maquina_id, nombre),
        )
        proceso_id = c.fetchone()[0]
        sincronizar_secuencia(c, "procesos")

        actividad_id = None
        estandar_id = None
        ordenes_actualizadas = 0

        if actividad_nombre:
            actividad_payload = dict(data)
            actividad_payload["proceso_id"] = proceso_id
            actividad_payload["nombre"] = actividad_nombre

            sincronizar_secuencia(c, "actividades")
            c.execute(
                "INSERT INTO actividades (proceso_id, nombre) VALUES (%s, %s) RETURNING id",
                (proceso_id, actividad_nombre),
            )
            actividad_id = c.fetchone()[0]
            sincronizar_secuencia(c, "actividades")
            estandar_id = crear_estandar(c, actividad_id, actividad_payload)
            ordenes_actualizadas = sincronizar_actividad_en_ordenes_abiertas(c, actividad_id)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "ok": True,
        "proceso_id": proceso_id,
        "actividad_id": actividad_id,
        "estandar_id": estandar_id,
        "ordenes_actualizadas": ordenes_actualizadas,
    }


@router.post("/config/asistente/actividad")
def crear_actividad_asistente(data: dict):
    proceso_id = entero_obligatorio(data, "proceso_id", "Proceso")
    nombre = texto_obligatorio(data, "nombre", "Nombre de la actividad")

    conn = db()
    c = conn.cursor()
    try:
        c.execute("SELECT id FROM procesos WHERE id = %s", (proceso_id,))
        if not c.fetchone():
            raise HTTPException(status_code=400, detail="El proceso seleccionado no existe")

        c.execute(
            """
            SELECT id
            FROM actividades
            WHERE proceso_id = %s
            AND lower(trim(nombre)) = lower(trim(%s))
            """,
            (proceso_id, nombre),
        )
        if c.fetchone():
            raise HTTPException(status_code=400, detail="Esa actividad ya existe en este proceso")

        sincronizar_secuencia(c, "actividades")
        c.execute(
            "INSERT INTO actividades (proceso_id, nombre) VALUES (%s, %s) RETURNING id",
            (proceso_id, nombre),
        )
        actividad_id = c.fetchone()[0]
        sincronizar_secuencia(c, "actividades")

        estandar_id = crear_estandar(c, actividad_id, data)
        ordenes_actualizadas = sincronizar_actividad_en_ordenes_abiertas(c, actividad_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "ok": True,
        "actividad_id": actividad_id,
        "estandar_id": estandar_id,
        "ordenes_actualizadas": ordenes_actualizadas,
    }


@router.get("/config/maquinas")
def ver_maquinas():
    conn = db()
    c = conn.cursor()
    c.execute("SELECT id, nombre FROM maquinas ORDER BY id")
    datos = c.fetchall()
    conn.close()
    return datos


@router.post("/config/maquinas")
def crear_maquina(nombre: str):
    conn = db()
    c = conn.cursor()
    sincronizar_secuencia(c, "maquinas")
    c.execute("INSERT INTO maquinas (nombre) VALUES (%s)", (nombre,))
    sincronizar_secuencia(c, "maquinas")
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
    return eliminar_fila("maquinas", id)


@router.get("/config/operarios")
def ver_operarios():
    conn = db()
    c = conn.cursor()
    c.execute("SELECT id, nombre FROM operarios ORDER BY id")
    datos = c.fetchall()
    conn.close()
    return datos


@router.post("/config/operarios")
def crear_operario(nombre: str):
    conn = db()
    c = conn.cursor()
    sincronizar_secuencia(c, "operarios")
    c.execute("INSERT INTO operarios (nombre) VALUES (%s)", (nombre,))
    sincronizar_secuencia(c, "operarios")
    conn.commit()
    conn.close()
    return {"mensaje": "operario creado"}


@router.delete("/config/operarios/{id}")
def eliminar_operario(id: int):
    return eliminar_fila("operarios", id)


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
    c.execute("SELECT id, proceso_id, nombre FROM actividades ORDER BY id")
    datos = c.fetchall()
    conn.close()
    return datos


@router.post("/config/actividades")
def crear_actividad(proceso_id: int, nombre: str):
    conn = db()
    c = conn.cursor()
    sincronizar_secuencia(c, "actividades")
    c.execute("INSERT INTO actividades (proceso_id, nombre) VALUES (%s, %s)", (proceso_id, nombre))
    sincronizar_secuencia(c, "actividades")
    conn.commit()
    conn.close()
    return {"mensaje": "actividad creada"}


@router.delete("/config/actividades/{id}")
def eliminar_actividad(id: int):
    return eliminar_fila("actividades", id)


@router.get("/config/tabla/{tabla}")
def ver_tabla(tabla: str):
    validar_tabla(tabla)
    conn = db()
    c = conn.cursor()
    c.execute(sql.SQL("SELECT * FROM {} ORDER BY id").format(sql.Identifier(tabla)))
    datos = c.fetchall()
    columnas = [col[0] for col in c.description]
    conn.close()
    return {"columnas": columnas, "datos": datos}


@router.post("/config/tabla/{tabla}")
def insertar_fila(tabla: str, datos: list):
    validar_tabla(tabla)
    conn = db()
    c = conn.cursor()
    try:
        sincronizar_secuencia(c, tabla)
        c.execute(sql.SQL("SELECT * FROM {} LIMIT 0").format(sql.Identifier(tabla)))
        columnas = [col[0] for col in c.description][1:]
        valores = [limpiar_valor(v) for v in datos]
        if len(valores) != len(columnas):
            raise HTTPException(status_code=400, detail="Numero de valores invalido")
        query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            sql.Identifier(tabla),
            sql.SQL(", ").join(sql.Identifier(col) for col in columnas),
            sql.SQL(", ").join(sql.Placeholder() for _ in columnas),
        )
        c.execute(query, valores)
        sincronizar_secuencia(c, tabla)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"mensaje": "fila creada"}


@router.delete("/config/tabla/{tabla}/{id}")
def eliminar_fila(tabla: str, id: int):
    validar_tabla(tabla)
    conn = db()
    c = conn.cursor()
    try:
        uso = fila_en_uso(c, tabla, id)
        if uso:
            tabla_ref, columna_ref, total = uso
            raise HTTPException(
                status_code=400,
                detail=f"No se puede eliminar: esta fila se usa en {tabla_ref}.{columna_ref} ({total} registros)",
            )

        c.execute(sql.SQL("DELETE FROM {} WHERE id=%s").format(sql.Identifier(tabla)), (id,))
        sincronizar_secuencia(c, tabla)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"mensaje": "fila eliminada"}


@router.post("/config/tabla/{tabla}/actualizar")
def actualizar_tabla(tabla: str, data: dict):
    return guardar_filas(tabla, data["columnas"], data["filas"])


@router.post("/config/tabla/{tabla}/guardar")
def guardar_tabla(tabla: str, data: dict):
    return guardar_filas(tabla, data["columnas"], data["filas"])


@router.get("/configuracion", response_class=HTMLResponse)
def configuracion(request: Request):
    if "username" not in request.session:
        return RedirectResponse("/admin?next=configuracion", 303)
    if request.session.get("role") != "admin":
        return RedirectResponse("/", 303)
    return request.app.state.templates.TemplateResponse(
        request=request, name="configuracion.html", context={"request": request}
    )
