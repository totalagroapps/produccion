from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from auth import require_admin
from database import db
from datetime import datetime
from routers.planificador import sincronizar_actividades_ordenes_abiertas

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    if not require_admin(request):
        return RedirectResponse("/admin", 303)

    rango = request.query_params.get("rango", "hoy")
    
    # Determinar filtros de fecha (asumiendo PostgreSQL, casteamos el texto a timestamp)
    if rango == 'ayer':
        date_filter = "inicio::timestamp >= CURRENT_DATE - INTERVAL '1 day' AND inicio::timestamp < CURRENT_DATE"
        prev_date_filter = "inicio::timestamp >= CURRENT_DATE - INTERVAL '2 days' AND inicio::timestamp < CURRENT_DATE - INTERVAL '1 day'"
    elif rango == '7dias':
        date_filter = "inicio::timestamp >= CURRENT_DATE - INTERVAL '7 days'"
        prev_date_filter = "inicio::timestamp >= CURRENT_DATE - INTERVAL '14 days' AND inicio::timestamp < CURRENT_DATE - INTERVAL '7 days'"
    elif rango == 'mes':
        date_filter = "inicio::timestamp >= DATE_TRUNC('month', CURRENT_DATE)"
        prev_date_filter = "inicio::timestamp >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1 month') AND inicio::timestamp < DATE_TRUNC('month', CURRENT_DATE)"
    else: # hoy
        rango = 'hoy'
        date_filter = "inicio::timestamp >= CURRENT_DATE"
        prev_date_filter = "inicio::timestamp >= CURRENT_DATE - INTERVAL '1 day' AND inicio::timestamp < CURRENT_DATE"

    conn = db()
    c = conn.cursor()

    # 1. Órdenes en producción (en este periodo)
    c.execute(f"SELECT COUNT(DISTINCT orden_id) FROM registros_produccion WHERE {date_filter}")
    ordenes_activas = c.fetchone()[0] or 0
    
    c.execute(f"SELECT COUNT(DISTINCT orden_id) FROM registros_produccion WHERE {prev_date_filter}")
    ordenes_prev = c.fetchone()[0] or 0
    
    tendencia_ordenes = 0
    if ordenes_prev > 0:
        tendencia_ordenes = round(((ordenes_activas - ordenes_prev) / ordenes_prev) * 100, 1)
    else:
        tendencia_ordenes = 100 if ordenes_activas > 0 else 0

    # 2. Producción del periodo
    c.execute(f"SELECT COALESCE(SUM(cantidad), 0) FROM registros_produccion WHERE {date_filter}")
    produccion_hoy = c.fetchone()[0]

    c.execute(f"SELECT COALESCE(SUM(cantidad), 0) FROM registros_produccion WHERE {prev_date_filter}")
    produccion_prev = c.fetchone()[0]

    tendencia_prod = 0
    if produccion_prev > 0:
        tendencia_prod = round(((produccion_hoy - produccion_prev) / produccion_prev) * 100, 1)
    else:
        tendencia_prod = 100 if produccion_hoy > 0 else 0

    # 3. Avance Global de Órdenes Abiertas
    c.execute("""
        SELECT COALESCE(SUM(cantidad_realizada), 0), COALESCE(SUM(cantidad_total), 0)
        FROM orden_actividades
        WHERE orden_id IN (SELECT id FROM ordenes WHERE estado != 'CERRADA')
    """)
    row_avance = c.fetchone()
    if row_avance and row_avance[1] > 0:
        avance_promedio = round((row_avance[0] / row_avance[1]) * 100, 1)
    else:
        avance_promedio = 0

    # 4. Tickets Abiertos (en lugar de Operarios Activos o como complemento)
    c.execute("SELECT COUNT(*) FROM tickets WHERE estado != 'Cerrado'")
    tickets_abiertos = c.fetchone()[0] or 0

    # Gráfico: Últimos 7 días
    c.execute("""
        SELECT DATE(inicio::timestamp) as fecha, COALESCE(SUM(cantidad), 0)
        FROM registros_produccion 
        WHERE inicio::timestamp >= CURRENT_DATE - INTERVAL '6 days'
        GROUP BY DATE(inicio::timestamp)
        ORDER BY fecha
    """)
    chart_rows = c.fetchall()
    # Preparar datos para Chart.js
    fechas = [r[0].strftime('%d/%m') for r in chart_rows]
    cantidades = [r[1] for r in chart_rows]

    # Alertas y Notificaciones Contextuales
    # Última orden
    c.execute("""
        SELECT o.id, m.nombre, o.cantidad
        FROM registros_produccion rp
        JOIN ordenes o ON o.id = rp.orden_id
        JOIN maquinas m ON m.id = o.maquina_id
        ORDER BY rp.fin DESC NULLS LAST
        LIMIT 1
    """)
    ultima_orden = c.fetchone()
    if ultima_orden:
        ultima_orden = {"id": ultima_orden[0], "maquina": ultima_orden[1], "cantidad": ultima_orden[2]}

    # Tickets recientes
    c.execute("""
        SELECT id, titulo, prioridad 
        FROM tickets 
        WHERE estado != 'Cerrado' 
        ORDER BY CASE WHEN prioridad = 'Alta' THEN 1 ELSE 2 END, id DESC 
        LIMIT 3
    """)
    tickets_recientes = [{"id": r[0], "titulo": r[1], "prioridad": r[2]} for r in c.fetchall()]

    conn.close()

    return request.app.state.templates.TemplateResponse(
        request=request, name="home.html", context={
        "request": request,
        "rango": rango,
        "ordenes_activas": ordenes_activas,
        "tendencia_ordenes": tendencia_ordenes,
        "produccion_hoy": produccion_hoy,
        "tendencia_prod": tendencia_prod,
        "avance_promedio": avance_promedio,
        "tickets_abiertos": tickets_abiertos,
        "chart_fechas": fechas,
        "chart_cantidades": cantidades,
        "ultima_orden": ultima_orden,
        "tickets_recientes": tickets_recientes
    })


# ================= PANEL =================

@router.get("/panel", response_class=HTMLResponse)
def panel(request: Request):

    if not require_admin(request):
        return RedirectResponse("/admin", 303)

    conn = db()
    c = conn.cursor()
    sincronizar_actividades_ordenes_abiertas(c)
    conn.commit()

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

    return request.app.state.templates.TemplateResponse(
        request=request, name="panel.html", context={
        "request": request,
        "maquinas": maquinas,
        "ordenes": ordenes
    })


# ================= METRICAS OPERARIOS =================

@router.get("/metricas_operarios", response_class=HTMLResponse)
def metricas_operarios(request: Request):

    conn = db()
    c = conn.cursor()

    semanas = metricas_semanales(c)

    conn.close()

    return request.app.state.templates.TemplateResponse(
        request=request, name="Metricas.html", context={
        "request": request,
        "semanas": semanas
    })


# ================= KPI DASHBOARD =================

@router.get("/kpi", response_class=HTMLResponse)
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

    return request.app.state.templates.TemplateResponse(
        request=request, name="kpi.html", context={
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


@router.get("/sincronizar_ordenes_abiertas")
def sincronizar_ordenes_abiertas_web(request: Request):

    if not require_admin(request):
        return RedirectResponse("/admin", 303)

    conn = db()
    c = conn.cursor()
    insertadas = sincronizar_actividades_ordenes_abiertas(c)
    conn.commit()
    conn.close()

    return RedirectResponse(f"/panel?sync={insertadas}", 303)


@router.get("/inicio_operario", response_class=HTMLResponse)
def inicio_operario(request: Request):
    if request.session.get("role") != "operario":
        return RedirectResponse("/admin", 303)
    return request.app.state.templates.TemplateResponse(
        request=request, name="inicio_operario.html", context={"request": request}
    )


@router.get("/registro_web", response_class=HTMLResponse)
def registro_web(request: Request):
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="registro_web.html",
        context={
            "request": request,
            "operario_actual": {
                "id": request.session.get("operario_id"),
                "nombre": request.session.get("operario_nombre") or request.session.get("username"),
            },
        },
    )


@app.post("/registro_web/registro")
def registro_web_guardar(data: dict, request: Request):
    if not require_operario(request):
        return JSONResponse(
            {"detail": "Debe iniciar sesion como operario"},
            status_code=401,
        )

    return guardar_registro_android(data, request.session["operario_id"])


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

@router.get("/exportar_excel")
def exportar_excel(periodo: str = "semanal", fecha: str = None):
    params = {"periodo": periodo}
    if fecha:
        params["fecha"] = fecha

    return RedirectResponse(f"/metricas/exportar_excel?{urlencode(params)}", 303)


# ================= ELIMINAR ORDEN =================

@app.post("/eliminar/{id}")
def eliminar(id: int):

    conn = db()
    c = conn.cursor()

    c.execute("DELETE FROM orden_actividades WHERE orden_id = %s", (id,))
    c.execute("DELETE FROM ordenes WHERE id = %s", (id,))

    conn.commit()
    conn.close()

    return RedirectResponse("/panel", 303)


# ================= CERRAR ORDEN =================

@router.get("/cerrar/{orden_id}")
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
    """, (datetime.now(ZoneInfo("America/Bogota")).strftime("%Y-%m-%d %H:%M:%S"), orden_id))

    conn.commit()
    conn.close()

    return RedirectResponse("/panel", status_code=303)


@router.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    if request.session.get("username"):
        role = request.session.get("role")
        if role == "admin": return RedirectResponse("/", status_code=303)
        elif role == "jefe_tickets": return RedirectResponse("/tickets/admin", status_code=303)
        elif role == "operario": return RedirectResponse("/inicio_operario", status_code=303)
        return RedirectResponse("/", status_code=303)
        
    return request.app.state.templates.TemplateResponse(
        request=request, name="login.html", context={"request": request})


@app.post("/admin")
@limiter.limit("5/minute")
def admin_post(request: Request, user: str = Form(...), password: str = Form(...)):

    if login_user(request, user, password):
        if request.session.get("role") == "operario" and request.session.get("debe_cambiar_password"):
            next_page = "/cambiar_password"
        else:
            next_page = request.query_params.get("next")
            
        if not next_page or next_page == "None":
            role = request.session.get("role")
            if role == "admin":
                next_page = "/"
            elif role == "jefe_tickets":
                next_page = "/tickets/admin"
            elif role == "operario":
                next_page = "/inicio_operario"
            else:
                next_page = "/"

        return RedirectResponse(next_page, status_code=303)

    return request.app.state.templates.TemplateResponse(
        request=request, name="login.html", context={"request": request, "error": "Usuario o contraseña incorrectos"}
    )


@router.get("/cambiar_password", response_class=HTMLResponse)
def cambiar_password_web(request: Request):
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="cambiar_password.html",
        context={"request": request, "error": ""},
    )


@app.post("/cambiar_password", response_class=HTMLResponse)
def cambiar_password_web_post(
    request: Request,
    nueva_password: str = Form(...),
    confirmar_password: str = Form(...),
):
    nueva_password = nueva_password.strip()
    confirmar_password = confirmar_password.strip()

    error = ""
    if not nueva_password:
        error = "Nuevo password requerido"
    elif len(nueva_password) < 4:
        error = "El password debe tener minimo 4 caracteres"
    elif nueva_password != confirmar_password:
        error = "Los passwords no coinciden"

    if error:
        return request.app.state.templates.TemplateResponse(
            request=request,
            name="cambiar_password.html",
            context={"request": request, "error": error},
            status_code=400,
        )

    conn = db()
    c = conn.cursor()
    c.execute(
        """
        UPDATE users
        SET password = %s,
            debe_cambiar_password = FALSE
        WHERE username = %s
          AND role = 'operario'
        """,
        (hash_password(nueva_password), request.session["username"]),
    )
    conn.commit()
    conn.close()

    request.session["debe_cambiar_password"] = False
    return RedirectResponse("/registro_web", status_code=303)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin", status_code=303)


# ================= REGISTRO PRODUCCION ANDROID =================

@app.post("/registro_android")
def registro_android(data: dict, usuario=Depends(usuario_android_habilitado)):
    return guardar_registro_android(data, usuario["operario_id"])


# ================= IMPORTAR =================

@router.get("/importar")
def importar(request: Request):
    return request.app.state.templates.TemplateResponse(
        request=request, name="importar.html", context={"request": request})


@router.get("/operarios")
def operarios():
    conn = db()
    c = conn.cursor()
    c.execute("SELECT id, nombre FROM operarios")
    rows = c.fetchall()
    conn.close()
    return rows


@router.get("/maquinas")
def maquinas():
    conn = db()
    c = conn.cursor()
    c.execute("SELECT id, nombre FROM maquinas")
    rows = c.fetchall()
    conn.close()
    return rows


@router.get("/ordenes")
def ordenes_android():
    conn = db()
    c = conn.cursor()
    sincronizar_actividades_ordenes_abiertas(c)
    conn.commit()
    c.execute("""
    SELECT id, maquina_id, estado, porcentaje
    FROM ordenes
    WHERE estado != 'CERRADA'
    """)
    rows = c.fetchall()
    conn.close()
    return rows


@router.get("/procesos/{orden_id}")
def procesos_android(orden_id: int):
    conn = db()
    c = conn.cursor()
    sincronizar_actividades_ordenes_abiertas(c, orden_id)
    conn.commit()
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


@router.get("/actividades/{orden}/{proceso}")
def actividades_android(orden: int, proceso: int):
    conn = db()
    c = conn.cursor()
    sincronizar_actividades_ordenes_abiertas(c, orden)
    conn.commit()
    c.execute("""
    SELECT a.id, a.nombre
    FROM orden_actividades oa
    JOIN actividades a ON a.id = oa.actividad_id
    WHERE oa.orden_id = %s AND a.proceso_id = %s
    """, (orden, proceso))
    rows = c.fetchall()
    conn.close()
    return rows



@router.get("/metricas", response_class=HTMLResponse)
def metricas(request: Request):

    conn = db()
    c = conn.cursor()

    semanas = metricas_semanales(c)

    conn.close()

    return request.app.state.templates.TemplateResponse(
        request=request, name="Metricas.html", context={
        "request": request,
        "semanas": semanas
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





@router.get("/ver_actividades")
def ver_actividades():
    conn = db()
    c = conn.cursor()
    c.execute("SELECT id, nombre FROM actividades")
    rows = c.fetchall()
    conn.close()
    return rows


@router.get("/ver_bonos")
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


@router.get("/ver_registros")
def ver_registros():
    conn = db()
    c = conn.cursor()
    c.execute("SELECT * FROM registros_produccion")
    rows = c.fetchall()
    conn.close()
    return rows


META_MENSUAL = 5000
TARIFA_HH = 10000


@router.get("/cargar_estandares_excel")
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


@router.get("/bonos", response_class=HTMLResponse)
def bonos(request: Request):

    if not require_admin(request):
        return RedirectResponse("/admin", 303)

    hoy = datetime.now(ZoneInfo("America/Bogota"))
    mes = int(request.query_params.get("mes", hoy.month))
    anio = int(request.query_params.get("anio", hoy.year))

    from routers.bonos import bonos_mes
    datos = bonos_mes(mes, anio)

    return request.app.state.templates.TemplateResponse(
        request=request, name="bonos.html", context={
        "request": request,
        "datos": datos,
        "mes": mes,
        "anio": anio
    })


@router.get("/bonos/detalle", response_class=HTMLResponse)
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
            COALESCE(m.nombre, '') as maquina,
            SUM(r.cantidad) as unidades,
            SUM(EXTRACT(EPOCH FROM (r.fin::timestamp - r.inicio::timestamp)) / 3600.0) as horas
        FROM registros_produccion r
        JOIN operarios o ON o.id = r.operario_id
        JOIN actividades a ON a.id = r.actividad_id
        LEFT JOIN procesos p ON p.id = a.proceso_id
        LEFT JOIN maquinas m ON m.id = p.maquina_id
        WHERE o.nombre = %s
        AND TO_CHAR(r.inicio::timestamp, 'MM') = %s
        AND TO_CHAR(r.inicio::timestamp, 'YYYY') = %s
        GROUP BY a.id, a.nombre, m.nombre
    """, (nombre, f"{mes:02d}", str(anio)))
    rows = c.fetchall()

    detalle = []
    total_bono = 0

    for actividad_id, actividad, maquina, unidades, horas in rows:

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
            "maquina": maquina,
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

    return request.app.state.templates.TemplateResponse(
        request=request, name="bono_detalle.html", context={
        "request": request,
        "nombre": nombre,
        "mes": mes,
        "anio": anio,
        "detalle": detalle,
        "total_bono": round(total_bono, 2)
    })


@router.get("/usuarios", response_class=HTMLResponse)
def ver_usuarios(request: Request):

    if not require_admin(request):
        return RedirectResponse("/admin", status_code=303)

    conn = db()
    c = conn.cursor()
    c.execute("""
        SELECT u.id, u.username, u.role, u.operario_id, COALESCE(o.nombre, '')
        FROM users u
        LEFT JOIN operarios o ON o.id = u.operario_id
        ORDER BY u.id
    """)
    usuarios = c.fetchall()

    c.execute("SELECT id, nombre FROM operarios ORDER BY nombre")
    operarios = c.fetchall()

    conn.close()

    return request.app.state.templates.TemplateResponse(
        request=request, name="usuarios.html", context={
        "request": request,
        "usuarios": usuarios,
        "operarios": operarios
    })


@app.post("/usuarios/crear")
def crear_usuario(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    operario_id: str = Form("")
):

    if not require_admin(request):
        return RedirectResponse("/admin", status_code=303)

    hashed = hash_password(password)
    operario_id_valor = int(operario_id) if operario_id else None

    if role == "operario" and not operario_id_valor:
        return "Seleccione un operario para usuarios con rol operario"

    if role != "operario":
        operario_id_valor = None

    conn = db()
    c = conn.cursor()

    try:
        c.execute(
            "INSERT INTO users (username, password, role, operario_id) VALUES (%s, %s, %s, %s)",
            (username, hashed, role, operario_id_valor)
        )
        conn.commit()
    except Exception as e:
        import logging
        logging.error(f"Error creando usuario: {e}", exc_info=True)
        conn.rollback()
    finally:
        conn.close()

    return RedirectResponse("/usuarios", status_code=303)




@router.get("/api/kardex/{referencia}")
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
