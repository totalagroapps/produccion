import re
import unicodedata

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from database import db
from auth import hash_password, require_admin

router = APIRouter()

templates = Jinja2Templates(directory="templates")

PASSWORD_TEMPORAL_DEFAULT = "123456"


def asegurar_schema_usuarios():
    conn = db()
    c = conn.cursor()
    c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS debe_cambiar_password BOOLEAN DEFAULT FALSE")
    c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS telefono TEXT")
    conn.commit()
    conn.close()


def slug_usuario(nombre: str) -> str:
    texto = unicodedata.normalize("NFKD", nombre or "")
    texto = texto.encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"[^a-zA-Z0-9]+", ".", texto).strip(".").lower()
    return texto or "operario"


def usuario_disponible(cursor, base: str) -> str:
    candidato = base
    sufijo = 2

    while True:
        cursor.execute("SELECT 1 FROM users WHERE username = %s", (candidato,))
        if not cursor.fetchone():
            return candidato

        candidato = f"{base}.{sufijo}"
        sufijo += 1


@router.get("/usuarios", response_class=HTMLResponse)
def ver_usuarios(request: Request):

    if not require_admin(request):
        return RedirectResponse("/admin", 303)

    asegurar_schema_usuarios()

    conn = db()
    c = conn.cursor()
    c.execute("""
        SELECT u.id, u.username, u.role, u.operario_id, COALESCE(o.nombre, ''),
               COALESCE(u.debe_cambiar_password, FALSE), COALESCE(u.telefono, '')
        FROM users u
        LEFT JOIN operarios o ON o.id = u.operario_id
        ORDER BY u.id
    """)
    usuarios = c.fetchall()

    c.execute("SELECT id, nombre FROM operarios ORDER BY nombre")
    operarios = c.fetchall()

    conn.close()

    return templates.TemplateResponse(
        request=request, name="usuarios.html", context={
        "request": request,
        "usuarios": usuarios,
        "operarios": operarios,
        "password_temporal_default": PASSWORD_TEMPORAL_DEFAULT
    })


from pydantic import BaseModel, Field, ValidationError
from fastapi.responses import JSONResponse

class UsuarioCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=4)
    role: str = Field(..., pattern="^(admin|operario|jefe_tickets)$")

@router.post("/usuarios/crear")
def crear_usuario(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    operario_id: str = Form(""),
    debe_cambiar_password: str = Form(""),
    telefono: str = Form("")
):

    if not require_admin(request):
        return RedirectResponse("/admin", 303)

    try:
        UsuarioCreate(username=username, password=password, role=role)
    except ValidationError as e:
        return JSONResponse(status_code=400, content={"detail": "Datos inválidos", "errores": e.errors()})

    asegurar_schema_usuarios()

    hashed = hash_password(password)
    operario_id_valor = int(operario_id) if operario_id else None

    if role == "operario" and not operario_id_valor:
        return "Seleccione un operario para usuarios con rol operario"

    if role != "operario":
        operario_id_valor = None

    debe_cambiar = role == "operario" and debe_cambiar_password == "on"

    conn = db()
    c = conn.cursor()

    try:
        c.execute(
            """
            INSERT INTO users
                (username, password, role, operario_id, debe_cambiar_password, telefono)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (username, hashed, role, operario_id_valor, debe_cambiar, telefono)
        )
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        return "El usuario ya existe"

    conn.close()
    return RedirectResponse("/usuarios", 303)


@router.post("/usuarios/crear_operarios")
def crear_usuarios_operarios(
    request: Request,
    password_temporal: str = Form(PASSWORD_TEMPORAL_DEFAULT)
):

    if not require_admin(request):
        return RedirectResponse("/admin", 303)

    asegurar_schema_usuarios()

    password_temporal = (password_temporal or PASSWORD_TEMPORAL_DEFAULT).strip()
    if len(password_temporal) < 4:
        return "El password temporal debe tener minimo 4 caracteres"

    conn = db()
    c = conn.cursor()
    c.execute("""
        SELECT o.id, o.nombre
        FROM operarios o
        LEFT JOIN users u ON u.operario_id = o.id
        WHERE u.id IS NULL
        ORDER BY o.nombre
    """)
    operarios_sin_usuario = c.fetchall()

    creados = 0
    hashed = hash_password(password_temporal)

    for operario_id, nombre in operarios_sin_usuario:
        username = usuario_disponible(c, slug_usuario(nombre))
        c.execute(
            """
            INSERT INTO users
                (username, password, role, operario_id, debe_cambiar_password)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (username, hashed, "operario", operario_id, True),
        )
        creados += 1

    conn.commit()
    conn.close()

    return RedirectResponse(f"/usuarios?creados={creados}", 303)


@router.post("/usuarios/reset_password/{user_id}")
def reset_password_usuario(request: Request, user_id: int):

    if not require_admin(request):
        return RedirectResponse("/admin", 303)

    asegurar_schema_usuarios()

    conn = db()
    c = conn.cursor()
    c.execute(
        """
        UPDATE users
        SET password = %s,
            debe_cambiar_password = TRUE
        WHERE id = %s AND role = 'operario'
        """,
        (hash_password(PASSWORD_TEMPORAL_DEFAULT), user_id),
    )
    conn.commit()
    conn.close()

    return RedirectResponse("/usuarios?reset=1", 303)


@router.post("/usuarios/eliminar/{user_id}")
def eliminar_usuario(request: Request, user_id: int):

    if not require_admin(request):
        return RedirectResponse("/admin", 303)

    conn = db()
    c = conn.cursor()

    # Obtener info del usuario a borrar
    c.execute("SELECT username, role FROM users WHERE id = %s", (user_id,))
    target_user = c.fetchone()
    if not target_user:
        conn.close()
        return RedirectResponse("/usuarios", 303)
        
    target_username, target_role = target_user

    # Regla 1: No auto-borrarse
    if target_username == request.session.get("username"):
        conn.close()
        return RedirectResponse("/usuarios?error=No+puedes+eliminar+tu+propio+usuario", 303)

    # Regla 2: No borrar al último admin
    if target_role == "admin":
        c.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
        admin_count = c.fetchone()[0]
        if admin_count <= 1:
            conn.close()
            return RedirectResponse("/usuarios?error=No+puedes+eliminar+al+ultimo+administrador", 303)

    c.execute("DELETE FROM users WHERE id = %s", (user_id,))
    conn.commit()
    conn.close()

    return RedirectResponse("/usuarios", 303)


@router.get("/usuarios/editar/{user_id}", response_class=HTMLResponse)
def editar_usuario_form(request: Request, user_id: int):
    if not require_admin(request):
        return RedirectResponse("/admin", 303)

    asegurar_schema_usuarios()
    
    conn = db()
    c = conn.cursor()
    
    c.execute("SELECT id, username, role, operario_id, telefono FROM users WHERE id = %s", (user_id,))
    usuario = c.fetchone()
    
    c.execute("SELECT id, nombre FROM operarios ORDER BY nombre")
    operarios = c.fetchall()
    conn.close()
    
    if not usuario:
        return RedirectResponse("/usuarios", 303)

    return templates.TemplateResponse(
        request=request, name="usuario_editar.html", context={
        "request": request,
        "usuario": usuario,
        "operarios": operarios
    })


@router.post("/usuarios/editar/{user_id}")
def editar_usuario_post(
    request: Request,
    user_id: int,
    role: str = Form(...),
    operario_id: str = Form(""),
    telefono: str = Form("")
):
    if not require_admin(request):
        return RedirectResponse("/admin", 303)

    asegurar_schema_usuarios()
    
    operario_id_valor = int(operario_id) if operario_id else None
    if role != "operario":
        operario_id_valor = None

    conn = db()
    c = conn.cursor()
    c.execute(
        """
        UPDATE users
        SET role = %s,
            operario_id = %s,
            telefono = %s
        WHERE id = %s
        """,
        (role, operario_id_valor, telefono, user_id)
    )
    conn.commit()
    conn.close()

    return RedirectResponse("/usuarios", 303)