from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from database import db
from auth import hash_password, require_admin

router = APIRouter()

templates = Jinja2Templates(directory="templates")

@router.get("/usuarios", response_class=HTMLResponse)
def ver_usuarios(request: Request):

    if not require_admin(request):
        return RedirectResponse("/admin", 303)

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

    return templates.TemplateResponse(
        request=request, name="usuarios.html", context={
        "request": request,
        "usuarios": usuarios,
        "operarios": operarios
    })


@router.post("/usuarios/crear")
def crear_usuario(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    operario_id: str = Form("")
):

    if not require_admin(request):
        return RedirectResponse("/admin", 303)

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
    except:
        conn.close()
        return "El usuario ya existe"

    conn.close()
    return RedirectResponse("/usuarios", 303)


@router.get("/usuarios/eliminar/{user_id}")
def eliminar_usuario(request: Request, user_id: int):

    if not require_admin(request):
        return RedirectResponse("/admin", 303)

    conn = db()
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id = %s", (user_id,))
    conn.commit()
    conn.close()

    return RedirectResponse("/usuarios", 303)
