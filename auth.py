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
    return request.session.get("role") == "admin"

def login_user(request: Request, username: str, password: str):
    conn = db()
    c = conn.cursor()

    c.execute("SELECT password, role FROM users WHERE username = %s", (username,))
    resultado = c.fetchone()
    conn.close()

    if resultado and verify_password(password, resultado[0]):
        request.session.clear()
        request.session["username"] = username
        request.session["role"] = resultado[1]
        return True

    return False