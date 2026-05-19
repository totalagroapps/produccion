import os
from datetime import datetime, timedelta

from fastapi import APIRouter, Header, HTTPException, Depends
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from auth import verify_password
from database import db

router = APIRouter()

ANDROID_TOKEN_SALT = "android-operario-token"
ANDROID_TOKEN_MAX_AGE = int(os.getenv("ANDROID_TOKEN_MAX_AGE", "2592000"))


def token_serializer():
    secret_key = os.getenv("SECRET_KEY")
    if not secret_key:
        raise HTTPException(status_code=500, detail="SECRET_KEY no configurado")
    return URLSafeTimedSerializer(secret_key)


def generar_token_android(user_id, username, role, operario_id):
    return token_serializer().dumps(
        {
            "user_id": user_id,
            "username": username,
            "role": role,
            "operario_id": operario_id,
        },
        salt=ANDROID_TOKEN_SALT,
    )


def leer_token_android(authorization: str = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Token Android requerido")

    token = authorization.split(" ", 1)[1].strip()

    try:
        return token_serializer().loads(
            token,
            salt=ANDROID_TOKEN_SALT,
            max_age=ANDROID_TOKEN_MAX_AGE,
        )
    except SignatureExpired as exc:
        raise HTTPException(status_code=401, detail="Sesion expirada") from exc
    except BadSignature as exc:
        raise HTTPException(status_code=401, detail="Token invalido") from exc


def usuario_android_actual(payload: dict = Depends(leer_token_android)):
    conn = db()
    c = conn.cursor()
    c.execute("""
        SELECT u.id, u.username, u.role, u.operario_id, o.nombre
        FROM users u
        LEFT JOIN operarios o ON o.id = u.operario_id
        WHERE u.id = %s
    """, (payload.get("user_id"),))
    row = c.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")

    user_id, username, role, operario_id, operario_nombre = row

    if role != "operario" or not operario_id:
        raise HTTPException(status_code=403, detail="Usuario Android sin operario asignado")

    return {
        "user_id": user_id,
        "username": username,
        "role": role,
        "operario_id": operario_id,
        "operario_nombre": operario_nombre,
    }


def campo_entero(data: dict, *nombres: str) -> int:
    for nombre in nombres:
        valor = data.get(nombre)
        if valor is not None and valor != "":
            return int(valor)

    raise HTTPException(
        status_code=400,
        detail=f"Campo requerido faltante: {'/'.join(nombres)}"
    )


def fecha_android(valor):
    if not valor:
        return None

    texto = str(valor).replace("Z", "+00:00")

    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        return datetime.strptime(str(valor), "%Y-%m-%d %H:%M:%S")


@router.post("/android/login")
def login_android(data: dict):
    username = str(data.get("username") or data.get("usuario") or "").strip()
    password = str(data.get("password") or data.get("clave") or "")

    if not username or not password:
        raise HTTPException(status_code=400, detail="Usuario y password son requeridos")

    conn = db()
    c = conn.cursor()
    c.execute("""
        SELECT u.id, u.username, u.password, u.role, u.operario_id, o.nombre
        FROM users u
        LEFT JOIN operarios o ON o.id = u.operario_id
        WHERE u.username = %s
    """, (username,))
    row = c.fetchone()
    conn.close()

    if not row or not verify_password(password, row[2]):
        raise HTTPException(status_code=401, detail="Usuario o password incorrecto")

    user_id, username, _, role, operario_id, operario_nombre = row

    if role != "operario" or not operario_id:
        raise HTTPException(status_code=403, detail="Este usuario no tiene operario asignado")

    token = generar_token_android(user_id, username, role, operario_id)

    return {
        "token": token,
        "token_type": "bearer",
        "expires_in": ANDROID_TOKEN_MAX_AGE,
        "usuario": {
            "id": user_id,
            "username": username,
            "role": role,
        },
        "operario": {
            "id": operario_id,
            "nombre": operario_nombre,
        },
    }


@router.get("/android/me")
def android_me(usuario=Depends(usuario_android_actual)):
    return {
        "usuario": {
            "id": usuario["user_id"],
            "username": usuario["username"],
            "role": usuario["role"],
        },
        "operario": {
            "id": usuario["operario_id"],
            "nombre": usuario["operario_nombre"],
        },
    }


# ================= REGISTRO ANDROID =================

def guardar_registro_android(data: dict, operario_id: int):

    try:
        orden_id = campo_entero(data, "orden_id", "orden")
        actividad_id = campo_entero(data, "actividad_id", "actividad")
        cantidad = campo_entero(data, "cantidad")
        tiempo = int(data.get("tiempo") or 0)
    except ValueError:
        raise HTTPException(status_code=400, detail="Campos numericos invalidos")

    conn = db()
    c = conn.cursor()

    inicio = fecha_android(data.get("inicio"))
    fin = fecha_android(data.get("fin"))

    if inicio and fin:
        tiempo = max(0, int((fin - inicio).total_seconds()))
    else:
        fin = datetime.now()
        inicio = fin - timedelta(seconds=tiempo)

    c.execute("""
    INSERT INTO registros_produccion
    (operario_id, orden_id, actividad_id, cantidad, inicio, fin, tiempo)
    VALUES (%s,%s,%s,%s,%s,%s,%s)
    """,(
        operario_id,
        orden_id,
        actividad_id,
        cantidad,
        inicio.strftime("%Y-%m-%d %H:%M:%S"),
        fin.strftime("%Y-%m-%d %H:%M:%S"),
        tiempo
    ))

    # actualizar actividad
    c.execute("""
    UPDATE orden_actividades
    SET cantidad_realizada = cantidad_realizada + %s
    WHERE orden_id=%s AND actividad_id=%s
    """,(
        cantidad,
        orden_id,
        actividad_id
    ))

    # recalcular porcentaje general
    c.execute("""
        SELECT SUM(cantidad_realizada),
               SUM(cantidad_total)
        FROM orden_actividades
        WHERE orden_id=%s
    """,(orden_id,))

    row = c.fetchone()

    if row and row[1] and row[1] > 0:
        porcentaje = round((row[0] / row[1]) * 100, 2)
    else:
        porcentaje = 0

    c.execute("""
        UPDATE ordenes
        SET porcentaje=%s,
            estado=CASE WHEN %s >= 100 THEN 'CERRADA' ELSE estado END
        WHERE id=%s
    """,(porcentaje, porcentaje, orden_id))

    conn.commit()
    conn.close()

    return {"status":"ok"}


@router.post("/registro_android")
def registro_android(data: dict, usuario=Depends(usuario_android_actual)):
    return guardar_registro_android(data, usuario["operario_id"])


# ================= LISTAS PARA ANDROID =================

@router.get("/operarios")
def operarios():
    conn = db()
    c = conn.cursor()

    c.execute("SELECT id,nombre FROM operarios")
    rows = c.fetchall() or []

    conn.close()

    return [{"id": r[0], "nombre": r[1]} for r in rows]


@router.get("/maquinas")
def maquinas():
    conn = db()
    c = conn.cursor()

    c.execute("SELECT id,nombre FROM maquinas")
    rows = c.fetchall() or []

    conn.close()

    return [{"id": r[0], "nombre": r[1]} for r in rows]


@router.get("/ordenes")
def ordenes_android():
    conn = db()
    c = conn.cursor()

    c.execute("""
    SELECT 
        o.id,
        o.maquina_id,
        m.nombre AS producto,
        COALESCE(o.cantidad, 0) AS cantidad,
        o.estado,
        o.porcentaje,
        o.cerrado_en
    FROM ordenes o
    JOIN maquinas m ON m.id = o.maquina_id
    WHERE o.estado != 'CERRADA'
    ORDER BY o.id DESC
    """)

    rows = c.fetchall() or []

    conn.close()

    return [
        {
            "id": r[0],
            "maquina_id": r[1],
            "producto": r[2],
            "cantidad": r[3],
            "estado": r[4],
            "porcentaje": r[5],
            "cerrado_en": r[6]
        }
        for r in rows
    ]


@router.get("/procesos/{orden_id}")
def procesos_android(orden_id:int):
    conn = db()
    c = conn.cursor()

    c.execute("""
    SELECT DISTINCT p.id,p.nombre
    FROM orden_actividades oa
    JOIN actividades a ON a.id=oa.actividad_id
    JOIN procesos p ON p.id=a.proceso_id
    WHERE oa.orden_id=%s
    """,(orden_id,))
    rows = c.fetchall() or []

    conn.close()

    return [{"id": r[0], "nombre": r[1]} for r in rows]


@router.get("/actividades/{orden}/{proceso}")
def actividades_android(orden:int, proceso:int):
    conn = db()
    c = conn.cursor()

    c.execute("""
    SELECT a.id,a.nombre
    FROM orden_actividades oa
    JOIN actividades a ON a.id=oa.actividad_id
    WHERE oa.orden_id=%s AND a.proceso_id=%s
    """,(orden,proceso))
    rows = c.fetchall() or []

    conn.close()

    return [{"id": r[0], "nombre": r[1]} for r in rows]
