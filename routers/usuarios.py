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
    c.execute("SELECT id, username, role FROM users")
    usuarios = c.fetchall()
    conn.close()

    return templates.TemplateResponse("usuarios.html", {
        "request": request,
        "usuarios": usuarios
    })


@router.post("/usuarios/crear")
def crear_usuario(request: Request, username: str = Form(...), password: str = Form(...), role: str = Form(...)):

    if not require_admin(request):
        return RedirectResponse("/admin", 303)

    hashed = hash_password(password)

    conn = db()
    c = conn.cursor()

    try:
        c.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            (username, hashed, role)
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
    c.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    return RedirectResponse("/usuarios", 303)