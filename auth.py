from fastapi import Request, Form
from fastapi.responses import RedirectResponse
from passlib.context import CryptContext
from database import db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)

def require_admin(request: Request):
    return bool(request.session.get("username")) and request.session.get("role") == "admin"

def require_operario(request: Request):
    return (
        bool(request.session.get("username"))
        and request.session.get("role") == "operario"
        and bool(request.session.get("operario_id"))
    )

def login_user(request: Request, username: str, password: str):
    conn = db()
    c = conn.cursor()

    c.execute("""
        SELECT u.password, u.role, u.operario_id, o.nombre,
               COALESCE(u.debe_cambiar_password, FALSE)
        FROM users u
        LEFT JOIN operarios o ON o.id = u.operario_id
        WHERE u.username = %s
    """, (username,))
    resultado = c.fetchone()
    conn.close()

    if resultado and verify_password(password, resultado[0]):
        request.session.clear()
        request.session["username"] = username
        request.session["role"] = resultado[1]
        if resultado[2]:
            request.session["operario_id"] = resultado[2]
            request.session["operario_nombre"] = resultado[3]
        request.session["debe_cambiar_password"] = bool(resultado[4])
        return True

    return False
