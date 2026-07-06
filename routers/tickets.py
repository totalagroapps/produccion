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

# Crear el directorio base si no existe
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
               u_asignado.username as asignado, u_creador.username as creador
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
        tid = row[0]
        if tid not in adjuntos_por_ticket:
            adjuntos_por_ticket[tid] = []
        adjuntos_por_ticket[tid].append({"nombre": row[1], "ruta": row[2]})

    # Reestructurar tickets
    tickets = []
    for t in tickets_rows:
        tickets.append({
            "id": t[0], "titulo": t[1], "descripcion": t[2], "estado": t[3],
            "fecha_creacion": t[4], "asignado": t[5], "creador": t[6],
            "adjuntos": adjuntos_por_ticket.get(t[0], [])
        })

    # Obtener usuarios operarios para asignar tickets
    c.execute("SELECT id, username FROM users WHERE role = 'operario' ORDER BY username")
    operarios = c.fetchall()

    conn.close()

    return templates.TemplateResponse(
        request=request, name="tickets_admin.html", context={
            "request": request,
            "tickets": tickets,
            "operarios": operarios
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

    # Guardar archivos
    if archivos:
        for archivo in archivos:
            if archivo.filename:
                # Generar nombre único
                timestamp = int(time.time())
                safe_filename = f"{timestamp}_{archivo.filename.replace(' ', '_')}"
                file_path = os.path.join(UPLOAD_DIR, safe_filename)
                
                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(archivo.file, buffer)
                
                # Guardar ruta relativa para poder cargar en la web
                web_path = f"/static/uploads/tickets/{safe_filename}"
                
                c.execute(
                    """
                    INSERT INTO ticket_adjuntos (ticket_id, nombre_original, ruta_archivo)
                    VALUES (%s, %s, %s)
                    """,
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
    # Los adjuntos se borran solos si pusiste ON DELETE CASCADE en la bd,
    # pero los archivos fisicos hay que borrarlos.
    c.execute("SELECT ruta_archivo FROM ticket_adjuntos WHERE ticket_id = %s", (ticket_id,))
    rutas = c.fetchall()
    
    for r in rutas:
        path = r[0].lstrip("/") # quitar el / inicial si lo tiene
        if os.path.exists(path):
            try:
                os.remove(path)
            except:
                pass

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

    c.execute("""
        SELECT t.id, t.titulo, t.descripcion, t.estado, t.fecha_creacion, u_creador.username as creador
        FROM tickets t
        LEFT JOIN users u_creador ON t.creado_por = u_creador.id
        WHERE t.asignado_a = %s
        ORDER BY t.fecha_creacion DESC
    """, (user_id,))
    tickets_rows = c.fetchall()

    # Obtener adjuntos
    c.execute("SELECT ticket_id, nombre_original, ruta_archivo FROM ticket_adjuntos")
    adjuntos_rows = c.fetchall()
    
    adjuntos_por_ticket = {}
    for row in adjuntos_rows:
        tid = row[0]
        if tid not in adjuntos_por_ticket:
            adjuntos_por_ticket[tid] = []
        adjuntos_por_ticket[tid].append({"nombre": row[1], "ruta": row[2]})

    # Reestructurar tickets
    tickets = []
    for t in tickets_rows:
        tickets.append({
            "id": t[0], "titulo": t[1], "descripcion": t[2], "estado": t[3],
            "fecha_creacion": t[4], "creador": t[5],
            "adjuntos": adjuntos_por_ticket.get(t[0], [])
        })

    conn.close()

    return templates.TemplateResponse(
        request=request, name="mis_tickets.html", context={
            "request": request,
            "tickets": tickets
        }
    )

@router.post("/tickets/actualizar_estado/{ticket_id}")
def actualizar_estado_ticket(
    request: Request,
    ticket_id: int,
    estado: str = Form(...)
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

    c.execute("""
        UPDATE tickets 
        SET estado = %s 
        WHERE id = %s AND asignado_a = %s
    """, (estado, ticket_id, user_id))
    
    conn.commit()
    conn.close()

    return RedirectResponse("/tickets/mis_tickets", 303)
