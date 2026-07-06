from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from database import db
from auth import require_jefe_tickets, require_operario
import os
import shutil
import time

router = APIRouter()
templates = Jinja2Templates(directory="templates")

UPLOAD_DIR = "static/uploads/tickets"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.get("/tickets/admin", response_class=HTMLResponse)
def panel_admin_tickets(request: Request):
    if not require_jefe_tickets(request):
        return RedirectResponse("/admin", 303)

    conn = db()
    c = conn.cursor()
    
    # Obtener tickets
    c.execute("""
        SELECT t.id, t.titulo, t.descripcion, t.estado, t.fecha_creacion, 
               u_asignado.username as asignado, u_creador.username as creador,
               t.notas_operario
        FROM tickets t
        LEFT JOIN users u_asignado ON t.asignado_a = u_asignado.id
        LEFT JOIN users u_creador ON t.creado_por = u_creador.id
        ORDER BY t.fecha_creacion DESC
    """)
    tickets_rows = c.fetchall()

    # Obtener adjuntos
    c.execute("SELECT ticket_id, nombre_original, ruta_archivo FROM ticket_adjuntos")
    adjuntos_rows = c.fetchall()
    adjuntos_por_ticket = {}
    for row in adjuntos_rows:
        tid, nombre, ruta = row
        adjuntos_por_ticket.setdefault(tid, []).append({"nombre": nombre, "ruta": ruta})

    # Obtener actividades
    c.execute("""
        SELECT a.id, a.ticket_id, a.descripcion, a.estado, u.username as asignado_a
        FROM ticket_actividades a
        LEFT JOIN users u ON a.asignado_a = u.id
        ORDER BY a.fecha_creacion ASC
    """)
    actividades_rows = c.fetchall()
    actividades_por_ticket = {}
    for row in actividades_rows:
        aid, tid, desc, est, asig = row
        actividades_por_ticket.setdefault(tid, []).append({
            "id": aid, "descripcion": desc, "estado": est, "asignado_a": asig
        })

    tickets = []
    for t in tickets_rows:
        tickets.append({
            "id": t[0], "titulo": t[1], "descripcion": t[2], "estado": t[3],
            "fecha_creacion": t[4], "asignado": t[5], "creador": t[6],
            "notas_operario": t[7],
            "adjuntos": adjuntos_por_ticket.get(t[0], []),
            "actividades": actividades_por_ticket.get(t[0], [])
        })

    c.execute("SELECT id, username FROM users WHERE role = 'operario' ORDER BY username")
    operarios = c.fetchall()
    conn.close()

    return templates.TemplateResponse(
        request=request, name="tickets_admin.html", context={
            "request": request, "tickets": tickets, "operarios": operarios
        }
    )

@router.post("/tickets/crear")
def crear_ticket(
    request: Request,
    titulo: str = Form(...),
    descripcion: str = Form(""),
    asignado_a: int = Form(...),
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

    c.execute(
        """
        INSERT INTO tickets (titulo, descripcion, estado, asignado_a, creado_por)
        VALUES (%s, %s, 'PENDIENTE', %s, %s) RETURNING id
        """,
        (titulo, descripcion, asignado_a, creado_por_id)
    )
    ticket_id = c.fetchone()[0]

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
                    "INSERT INTO ticket_adjuntos (ticket_id, nombre_original, ruta_archivo) VALUES (%s, %s, %s)",
                    (ticket_id, archivo.filename, web_path)
                )

    conn.commit()
    conn.close()
    return RedirectResponse("/tickets/admin", 303)

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

    # Modificado para incluir tickets donde es asignado principal o tiene actividades
    c.execute("""
        SELECT DISTINCT t.id, t.titulo, t.descripcion, t.estado, t.fecha_creacion, u_creador.username as creador, t.notas_operario
        FROM tickets t
        LEFT JOIN users u_creador ON t.creado_por = u_creador.id
        LEFT JOIN ticket_actividades a ON t.id = a.ticket_id
        WHERE t.asignado_a = %s OR a.asignado_a = %s
        ORDER BY t.fecha_creacion DESC
    """, (user_id, user_id))
    tickets_rows = c.fetchall()

    c.execute("SELECT ticket_id, nombre_original, ruta_archivo FROM ticket_adjuntos")
    adjuntos_rows = c.fetchall()
    adjuntos_por_ticket = {}
    for row in adjuntos_rows:
        tid, nombre, ruta = row
        adjuntos_por_ticket.setdefault(tid, []).append({"nombre": nombre, "ruta": ruta})

    c.execute("""
        SELECT a.id, a.ticket_id, a.descripcion, a.estado, u.username as asignado_a
        FROM ticket_actividades a
        LEFT JOIN users u ON a.asignado_a = u.id
        ORDER BY a.fecha_creacion ASC
    """)
    actividades_rows = c.fetchall()
    actividades_por_ticket = {}
    for row in actividades_rows:
        aid, tid, desc, est, asig = row
        actividades_por_ticket.setdefault(tid, []).append({
            "id": aid, "descripcion": desc, "estado": est, "asignado_a": asig
        })

    tickets = []
    for t in tickets_rows:
        tickets.append({
            "id": t[0], "titulo": t[1], "descripcion": t[2], "estado": t[3],
            "fecha_creacion": t[4], "creador": t[5], "notas_operario": t[6],
            "adjuntos": adjuntos_por_ticket.get(t[0], []),
            "actividades": actividades_por_ticket.get(t[0], [])
        })

    c.execute("SELECT id, username FROM users WHERE role = 'operario' ORDER BY username")
    operarios = c.fetchall()

    conn.close()

    return templates.TemplateResponse(
        request=request, name="mis_tickets.html", context={
            "request": request, "tickets": tickets, "operarios": operarios, "current_user_id": user_id
        }
    )

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

    # Solo el responsable del ticket principal puede cambiar estado del ticket, pero dejamos
    # que delegados puedan escribir notas si fuera necesario (opcional). Por seguridad, 
    # dejamos la condicion original: t.asignado_a = user_id
    c.execute("""
        UPDATE tickets 
        SET estado = %s, notas_operario = %s
        WHERE id = %s AND asignado_a = %s
    """, (estado, notas_operario, ticket_id, user_id))
    
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
                    "INSERT INTO ticket_adjuntos (ticket_id, nombre_original, ruta_archivo) VALUES (%s, %s, %s)",
                    (ticket_id, archivo.filename, web_path)
                )

    conn.commit()
    conn.close()
    return RedirectResponse("/tickets/mis_tickets", 303)

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

    c.execute(
        """
        INSERT INTO ticket_actividades (ticket_id, descripcion, asignado_a, creado_por)
        VALUES (%s, %s, %s, %s)
        """,
        (ticket_id, descripcion, asignado_a, creado_por_id)
    )
    conn.commit()
    conn.close()

    referer = request.headers.get("referer", "/tickets/mis_tickets")
    return RedirectResponse(referer, 303)

@router.post("/tickets/actividades/{actividad_id}/completar")
def completar_actividad(request: Request, actividad_id: int, estado: str = Form(...)):
    if not (require_jefe_tickets(request) or require_operario(request)):
        return RedirectResponse("/admin", 303)

    nuevo_estado = "COMPLETADA" if estado == "on" else "PENDIENTE"
    conn = db()
    c = conn.cursor()
    c.execute("UPDATE ticket_actividades SET estado = %s WHERE id = %s", (nuevo_estado, actividad_id))
    conn.commit()
    conn.close()

    referer = request.headers.get("referer", "/tickets/mis_tickets")
    return RedirectResponse(referer, 303)
