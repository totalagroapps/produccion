from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from database import db
from auth import require_jefe_tickets, require_operario
from utils_wpp import notificar_ticket_asignado
import os
import shutil
import time

router = APIRouter()
templates = Jinja2Templates(directory="templates")

UPLOAD_DIR = "static/uploads/tickets"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def _formato_ticket(t_row):
    import datetime
    from zoneinfo import ZoneInfo
    
    fecha_vencimiento = t_row[9] if len(t_row) > 9 else None
    estado_vencimiento = "OK"
    if fecha_vencimiento and t_row[3] not in ("CERRADO", "COMPLETADO"):
        now = datetime.datetime.now(ZoneInfo("America/Bogota")).replace(tzinfo=None)
        if now > fecha_vencimiento:
            estado_vencimiento = "VENCIDO"
        elif (fecha_vencimiento - now).total_seconds() < 86400: # menos de 24h
            estado_vencimiento = "POR_VENCER"
            
    return {
        "id": t_row[0],
        "consecutivo": f"TK-{t_row[0]:04d}",
        "titulo": t_row[1],
        "descripcion": t_row[2],
        "estado": t_row[3],
        "fecha_creacion": t_row[4],
        "asignado": t_row[5],
        "creador": t_row[6] if len(t_row) > 6 else None,
        "notas_operario": t_row[7] if len(t_row) > 7 else None,
        "prioridad": t_row[8] if len(t_row) > 8 else 'MEDIA',
        "fecha_vencimiento": fecha_vencimiento,
        "estado_vencimiento": estado_vencimiento
    }

@router.get("/tickets/admin", response_class=HTMLResponse)
def panel_admin_tickets(request: Request):
    if not require_jefe_tickets(request):
        return RedirectResponse("/admin", 303)

    conn = db()
    c = conn.cursor()
    
    # Obtener tickets (resumen)
    c.execute("""
        SELECT t.id, t.titulo, t.descripcion, t.estado, t.fecha_creacion, 
               u_asignado.username as asignado, u_creador.username as creador,
               t.notas_operario, t.prioridad, t.fecha_vencimiento
        FROM tickets t
        LEFT JOIN users u_asignado ON t.asignado_a = u_asignado.id
        LEFT JOIN users u_creador ON t.creado_por = u_creador.id
        ORDER BY t.fecha_creacion DESC
    """)
    tickets_rows = c.fetchall()

    tickets = []
    for t in tickets_rows:
        tickets.append(_formato_ticket(t))

    c.execute("SELECT id, username FROM users WHERE role = 'operario' ORDER BY username")
    operarios = c.fetchall()
    conn.close()

    return templates.TemplateResponse(
        request=request, name="tickets_admin.html", context={
            "request": request, "tickets": tickets, "operarios": operarios
        }
    )

@router.get("/tickets/mis_tickets", response_class=HTMLResponse)
def mis_tickets(request: Request):
    if not require_operario(request):
        return RedirectResponse("/admin", 303)

    username = request.session.get("username")
    conn = db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username = %s", (username,))
    row = c.fetchone()
    user_id = row[0] if row else None

    # Obtener tickets (resumen)
    c.execute("""
        SELECT DISTINCT t.id, t.titulo, t.descripcion, t.estado, t.fecha_creacion, 
               u_asignado.username as asignado, u_creador.username as creador,
               t.notas_operario, t.prioridad, t.fecha_vencimiento
        FROM tickets t
        LEFT JOIN users u_asignado ON t.asignado_a = u_asignado.id
        LEFT JOIN users u_creador ON t.creado_por = u_creador.id
        LEFT JOIN ticket_actividades a ON t.id = a.ticket_id
        WHERE t.asignado_a = %s OR a.asignado_a = %s
        ORDER BY t.fecha_creacion DESC
    """, (user_id, user_id))
    tickets_rows = c.fetchall()

    tickets = []
    for t in tickets_rows:
        tickets.append(_formato_ticket(t))

    conn.close()

    return templates.TemplateResponse(
        request=request, name="mis_tickets.html", context={
            "request": request, "tickets": tickets
        }
    )

@router.get("/tickets/detalle/{ticket_id}", response_class=HTMLResponse)
def detalle_ticket(request: Request, ticket_id: int):
    es_jefe = require_jefe_tickets(request)
    es_operario = require_operario(request)
    if not (es_jefe or es_operario):
        return RedirectResponse("/admin", 303)

    username = request.session.get("username")
    conn = db()
    c = conn.cursor()
    
    c.execute("SELECT id FROM users WHERE username = %s", (username,))
    row = c.fetchone()
    user_id = row[0] if row else None

    # Si es operario, verificar que tenga acceso a este ticket
    if es_operario and not es_jefe:
        c.execute("""
            SELECT COUNT(*) FROM tickets t
            LEFT JOIN ticket_actividades a ON t.id = a.ticket_id
            WHERE t.id = %s AND (t.asignado_a = %s OR a.asignado_a = %s)
        """, (ticket_id, user_id, user_id))
        if c.fetchone()[0] == 0:
            conn.close()
            raise HTTPException(status_code=403, detail="No tienes acceso a este ticket.")

    # Obtener datos del ticket
    c.execute("""
        SELECT t.id, t.titulo, t.descripcion, t.estado, t.fecha_creacion, 
               u_asignado.username as asignado, u_creador.username as creador,
               t.notas_operario, t.prioridad, t.fecha_vencimiento, t.asignado_a, u_asignado.telefono
        FROM tickets t
        LEFT JOIN users u_asignado ON t.asignado_a = u_asignado.id
        LEFT JOIN users u_creador ON t.creado_por = u_creador.id
        WHERE t.id = %s
    """, (ticket_id,))
    t_row = c.fetchone()
    if not t_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Ticket no encontrado")

    ticket = _formato_ticket(t_row)
    ticket["id_asignado_principal"] = t_row[10] if len(t_row) > 10 else None
    ticket["telefono_asignado"] = t_row[11] if len(t_row) > 11 else None

    # Adjuntos
    c.execute("""
        SELECT a.nombre_original, a.ruta_archivo, a.fecha_subida, u.username as subido_por_nombre 
        FROM ticket_adjuntos a
        LEFT JOIN users u ON a.subido_por = u.id
        WHERE a.ticket_id = %s
        ORDER BY a.fecha_subida ASC
    """, (ticket_id,))
    ticket["adjuntos"] = [{"nombre": r[0], "ruta": r[1], "fecha": r[2], "subido_por": r[3]} for r in c.fetchall()]

    # Notas
    c.execute("""
        SELECT n.id, n.nota, n.fecha_creacion, u.username as autor
        FROM ticket_notas n
        LEFT JOIN users u ON n.usuario_id = u.id
        WHERE n.ticket_id = %s
        ORDER BY n.fecha_creacion ASC
    """, (ticket_id,))
    ticket["notas"] = [{"id": r[0], "nota": r[1], "fecha": r[2], "autor": r[3]} for r in c.fetchall()]

    # Actividades
    c.execute("""
        SELECT a.id, a.descripcion, a.estado, u.username as asignado_a, a.asignado_a as id_asignado
        FROM ticket_actividades a
        LEFT JOIN users u ON a.asignado_a = u.id
        WHERE a.ticket_id = %s
        ORDER BY a.fecha_creacion ASC
    """, (ticket_id,))
    ticket["actividades"] = []
    for r in c.fetchall():
        ticket["actividades"].append({
            "id": r[0], "descripcion": r[1], "estado": r[2], "asignado_a": r[3], "id_asignado": r[4]
        })

    c.execute("SELECT id, username FROM users WHERE role = 'operario' ORDER BY username")
    operarios = c.fetchall()
    
    conn.close()

    return templates.TemplateResponse(
        request=request, name="ticket_detalle.html", context={
            "request": request, "ticket": ticket, "operarios": operarios, 
            "current_user_id": user_id, "es_jefe": es_jefe
        }
    )

@router.post("/tickets/crear")
def crear_ticket(
    request: Request,
    titulo: str = Form(...),
    descripcion: str = Form(""),
    asignado_a: int = Form(...),
    prioridad: str = Form("MEDIA"),
    fecha_vencimiento: str = Form(""),
    archivos: list[UploadFile] = File(None)
):
    if not require_jefe_tickets(request):
        return RedirectResponse("/admin", 303)

    creado_por_username = request.session.get("username")
    conn = db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username = %s", (creado_por_username,))
    row = c.fetchone()
    creado_por_id = row[0] if row else None

    fv = fecha_vencimiento if fecha_vencimiento else None

    c.execute(
        """
        INSERT INTO tickets (titulo, descripcion, estado, prioridad, fecha_vencimiento, asignado_a, creado_por)
        VALUES (%s, %s, 'PENDIENTE', %s, %s, %s, %s) RETURNING id
        """,
        (titulo, descripcion, prioridad, fv, asignado_a, creado_por_id)
    )
    ticket_id = c.fetchone()[0]

    c.execute("SELECT telefono FROM users WHERE id = %s", (asignado_a,))
    tel_row = c.fetchone()
    if tel_row and tel_row[0]:
        notificar_ticket_asignado(tel_row[0], f"TK-{ticket_id:04d}", titulo)

    if archivos:
        for archivo in archivos:
            if archivo.filename:
                timestamp = int(time.time())
                safe_filename = f"{timestamp}_{archivo.filename.replace(' ', '_')}"
                file_path = os.path.join(UPLOAD_DIR, safe_filename)
                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(archivo.file, buffer)
                web_path = f"/static/uploads/tickets/{safe_filename}"
                c.execute(
                    "INSERT INTO ticket_adjuntos (ticket_id, nombre_original, ruta_archivo, subido_por) VALUES (%s, %s, %s, %s)",
                    (ticket_id, archivo.filename, web_path, creado_por_id)
                )

    conn.commit()
    conn.close()
    return RedirectResponse(f"/tickets/detalle/{ticket_id}", 303)


@router.post("/tickets/kanban_update/{ticket_id}")
def kanban_update(request: Request, ticket_id: int, estado: str = Form(...)):
    if not require_jefe_tickets(request):
        return RedirectResponse("/admin", 303)

    estados_validos = ["PENDIENTE", "EN PROGRESO", "CERRADO"]
    if estado not in estados_validos:
        raise HTTPException(status_code=400, detail="Estado no válido")

    conn = db()
    c = conn.cursor()
    c.execute("UPDATE tickets SET estado = %s WHERE id = %s", (estado, ticket_id))
    conn.commit()
    conn.close()
    return {"status": "ok", "estado": estado}


@router.post("/tickets/eliminar/{ticket_id}")
def eliminar_ticket(request: Request, ticket_id: int):
    if not require_jefe_tickets(request):
        return RedirectResponse("/admin", 303)

    conn = db()
    c = conn.cursor()
    c.execute("SELECT ruta_archivo FROM ticket_adjuntos WHERE ticket_id = %s", (ticket_id,))
    rutas = c.fetchall()
    for r in rutas:
        path = r[0].lstrip("/")
        if os.path.exists(path):
            try: os.remove(path)
            except: pass

    c.execute("DELETE FROM tickets WHERE id = %s", (ticket_id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/tickets/admin", 303)

@router.post("/tickets/actualizar_estado/{ticket_id}")
def actualizar_estado_ticket(
    request: Request,
    ticket_id: int,
    estado: str = Form(...),
    notas_operario: str = Form(""),
    archivos: list[UploadFile] = File(None)
):
    if not require_operario(request):
        return RedirectResponse("/admin", 303)

    if estado not in ('PENDIENTE', 'EN_PROGRESO', 'COMPLETADO'):
        estado = 'PENDIENTE'

    username = request.session.get("username")
    conn = db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username = %s", (username,))
    row = c.fetchone()
    user_id = row[0] if row else None

    # Solo el responsable del ticket principal puede cambiar estado y notas generales
    c.execute("""
        UPDATE tickets 
        SET estado = %s
        WHERE id = %s AND asignado_a = %s AND estado != 'COMPLETADO'
    """, (estado, ticket_id, user_id))
    
    # Si hubo modificación de estado válida (o era el mismo), procedemos. 
    # Usamos c.rowcount para saber si pudo cambiar el estado.
    if c.rowcount > 0:
        if notas_operario.strip():
            c.execute(
                "INSERT INTO ticket_notas (ticket_id, usuario_id, nota) VALUES (%s, %s, %s)",
                (ticket_id, user_id, notas_operario.strip())
            )
    
    if archivos:
        # Check si se actualizó algo (es decir, sí tenía permiso)
        if c.rowcount > 0:
            for archivo in archivos:
                if archivo.filename:
                    timestamp = int(time.time())
                    safe_filename = f"{timestamp}_{archivo.filename.replace(' ', '_')}"
                    file_path = os.path.join(UPLOAD_DIR, safe_filename)
                    with open(file_path, "wb") as buffer:
                        shutil.copyfileobj(archivo.file, buffer)
                    web_path = f"/static/uploads/tickets/{safe_filename}"
                    c.execute(
                        "INSERT INTO ticket_adjuntos (ticket_id, nombre_original, ruta_archivo, subido_por) VALUES (%s, %s, %s, %s)",
                        (ticket_id, archivo.filename, web_path, user_id)
                    )

    conn.commit()
    conn.close()
    return RedirectResponse(f"/tickets/detalle/{ticket_id}", 303)

@router.post("/tickets/{ticket_id}/actividades/crear")
def crear_actividad(
    request: Request,
    ticket_id: int,
    descripcion: str = Form(...),
    asignado_a: int = Form(...)
):
    if not (require_jefe_tickets(request) or require_operario(request)):
        return RedirectResponse("/admin", 303)

    creado_por_username = request.session.get("username")
    conn = db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username = %s", (creado_por_username,))
    row = c.fetchone()
    creado_por_id = row[0] if row else None

    # Prevenir modificaciones en tickets cerrados
    c.execute("SELECT estado FROM tickets WHERE id = %s", (ticket_id,))
    t_estado = c.fetchone()
    if t_estado and t_estado[0] != 'COMPLETADO':
        c.execute(
            """
            INSERT INTO ticket_actividades (ticket_id, descripcion, asignado_a, creado_por)
            VALUES (%s, %s, %s, %s)
            """,
            (ticket_id, descripcion, asignado_a, creado_por_id)
        )
        conn.commit()
    
    conn.close()
    return RedirectResponse(f"/tickets/detalle/{ticket_id}", 303)

@router.post("/tickets/actividades/{actividad_id}/completar")
def completar_actividad(request: Request, actividad_id: int, estado: str = Form(...)):
    if not (require_jefe_tickets(request) or require_operario(request)):
        return RedirectResponse("/admin", 303)

    nuevo_estado = "COMPLETADA" if estado == "on" else "PENDIENTE"
    conn = db()
    c = conn.cursor()

    # Prevenir si el ticket principal está cerrado
    c.execute("""
        SELECT t.estado, t.id FROM tickets t 
        JOIN ticket_actividades a ON t.id = a.ticket_id 
        WHERE a.id = %s
    """, (actividad_id,))
    row = c.fetchone()
    ticket_id = None
    if row:
        t_estado, ticket_id = row
        if t_estado != 'COMPLETADO':
            c.execute("UPDATE ticket_actividades SET estado = %s WHERE id = %s", (nuevo_estado, actividad_id))
            conn.commit()

    conn.close()
    
    if ticket_id:
        return RedirectResponse(f"/tickets/detalle/{ticket_id}", 303)

@router.post("/tickets/actualizar_vencimiento/{ticket_id}")
def actualizar_vencimiento(request: Request, ticket_id: int, fecha_vencimiento: str = Form("")):
    if not require_jefe_tickets(request):
        return RedirectResponse("/admin", 303)

    conn = db()
    c = conn.cursor()
    fv = fecha_vencimiento if fecha_vencimiento else None
    c.execute("UPDATE tickets SET fecha_vencimiento = %s WHERE id = %s", (fv, ticket_id))
    conn.commit()
    conn.close()
    return RedirectResponse(f"/tickets/detalle/{ticket_id}", 303)
    return RedirectResponse("/tickets/admin", 303)
