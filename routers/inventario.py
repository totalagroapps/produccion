from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from database import db
import pandas as pd
import urllib.parse

router = APIRouter()

STOCK_MINIMO = 50


# ================= INVENTARIO PRINCIPAL =================

@router.get("/inventario", response_class=HTMLResponse)
def inventario(request: Request):

    if request.session.get("role") != "admin":
        return RedirectResponse("/admin", 303)

    conn = db()
    c = conn.cursor()

    # 🔹 Obtener productos base
    productos = productos = c.execute("""
            SELECT 
                i.referencia,
                i.peso_unitario_gr,
                i.precio_unitario,

                IFNULL(SUM(CASE WHEN m.tipo='INGRESO' THEN m.cantidad ELSE 0 END),0) as ingresos,
                IFNULL(SUM(CASE WHEN m.tipo='SALIDA' THEN m.cantidad ELSE 0 END),0) as salidas

            FROM inventario i
            LEFT JOIN movimientos_inventario m
                ON i.referencia = m.referencia

            GROUP BY i.referencia
        """).fetchall()

    inventario_final = []
    total_refs = 0
    valor_total_general = 0
    peso_total_general = 0
    bajo_stock_count = 0

    for p in productos:
        ref = p[0]
        peso_unitario = p[1] or 0
        precio_unitario = p[2] or 0

        # 🔹 Calcular stock desde movimientos
        c.execute("""
            SELECT 
                SUM(CASE WHEN tipo='INGRESO' THEN cantidad ELSE 0 END),
                SUM(CASE WHEN tipo='SALIDA' THEN cantidad ELSE 0 END)
            FROM movimientos_inventario
            WHERE referencia=?
        """, (ref,))

        row = c.fetchone()
        ingresos = row[0] or 0
        salidas = row[1] or 0
        disponibles = ingresos - salidas

        peso_total = (disponibles * peso_unitario) / 1000
        valor_total = disponibles * precio_unitario
        bajo_stock = disponibles <= STOCK_MINIMO

        if bajo_stock:
            bajo_stock_count += 1

        total_refs += 1
        valor_total_general += valor_total
        peso_total_general += peso_total

        inventario_final.append({
            "referencia": ref,
            "cantidad_total": ingresos,
            "entregadas": salidas,
            "disponibles": disponibles,
            "peso_total": peso_total,
            "precio": precio_unitario,
            "valor_total": valor_total,
            "bajo_stock": bajo_stock
        })

    conn.close()

    return request.app.state.templates.TemplateResponse(
        "inventario.html",
        {
            "request": request,
            "inventario": inventario_final,
            "total_refs": total_refs,
            "valor_total": valor_total_general,
            "peso_total": peso_total_general,
            "bajo_stock_count": bajo_stock_count
        }
    )


# ================= REGISTRAR MOVIMIENTO =================

@router.post("/inventario/movimiento")
def registrar_movimiento(
    request: Request,
    referencia: str = Form(...),
    tipo: str = Form(...),
    cantidad: int = Form(...)
):

    if request.session.get("role") != "admin":
        return RedirectResponse("/admin", 303)

    if cantidad <= 0:
        return RedirectResponse("/inventario", 303)

    conn = db()
    c = conn.cursor()

    usuario = request.session.get("username")

    c.execute("""
        INSERT INTO movimientos_inventario
        (referencia, tipo, cantidad, usuario)
        VALUES (?,?,?,?)
    """, (referencia, tipo, cantidad, usuario))

    # Recalcular stock
    c.execute("""
        UPDATE inventario
        SET total_disponibles = (
            SELECT IFNULL(SUM(
                CASE WHEN tipo='INGRESO' THEN cantidad ELSE -cantidad END
            ),0)
            FROM movimientos_inventario
            WHERE referencia=?
        )
        WHERE referencia=?
    """, (referencia, referencia))

    conn.commit()
    conn.close()

    return RedirectResponse("/inventario", 303)


# ================= KARDEX =================

@router.get("/inventario/kardex/{referencia:path}", response_class=HTMLResponse)
def kardex_producto(request: Request, referencia: str):

    if request.session.get("role") != "admin":
        return RedirectResponse("/admin", 303)

    conn = db()
    c = conn.cursor()

    movimientos = c.execute("""
        SELECT tipo, cantidad, usuario, fecha
        FROM movimientos_inventario
        WHERE referencia=?
        ORDER BY id ASC
    """, (referencia,)).fetchall()

    saldo = 0
    kardex = []

    for tipo, cantidad, usuario, fecha in movimientos:
        if tipo == "INGRESO":
            saldo += cantidad
        else:
            saldo -= cantidad

        kardex.append({
            "fecha": fecha,
            "tipo": tipo,
            "cantidad": cantidad,
            "usuario": usuario,
            "saldo": saldo
        })

    conn.close()

    return request.app.state.templates.TemplateResponse(
        "kardex.html",
        {
            "request": request,
            "referencia": referencia,
            "kardex": kardex
        }
    )


# ================= NUEVO PRODUCTO =================

@router.post("/inventario/nuevo")
def nuevo_producto(
    request: Request,
    referencia: str = Form(...),
    peso: float = Form(...),
    precio: float = Form(...),
    cantidad: int = Form(...)
):

    if request.session.get("role") != "admin":
        return RedirectResponse("/admin", 303)

    conn = db()
    c = conn.cursor()

    c.execute("""
        INSERT INTO inventario
        (referencia, peso_unitario_gr, cantidad_total, entregadas, total_disponibles, precio_unitario)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        referencia,
        peso,
        cantidad,
        0,
        cantidad,
        precio
    ))

    # Crear movimiento inicial automático
    usuario = request.session.get("username")

    c.execute("""
        INSERT INTO movimientos_inventario
        (referencia, tipo, cantidad, usuario)
        VALUES (?, 'INGRESO', ?, ?)
    """, (
        referencia,
        cantidad,
        f"{usuario} (CREACIÓN PRODUCTO)"
    ))

    conn.commit()
    conn.close()

    return RedirectResponse("/inventario", 303)


# ================= EDITAR PRODUCTO =================

@router.get("/inventario/editar/{referencia:path}", response_class=HTMLResponse)
def editar_producto(request: Request, referencia: str):

    if request.session.get("role") != "admin":
        return RedirectResponse("/admin", 303)

    conn = db()
    c = conn.cursor()

    producto = c.execute("""
        SELECT referencia,
               peso_unitario_gr,
               precio_unitario
        FROM inventario
        WHERE referencia=?
    """, (referencia,)).fetchone()

    conn.close()

    if not producto:
        return RedirectResponse("/inventario", 303)

    return request.app.state.templates.TemplateResponse(
        "editar_producto.html",
        {
            "request": request,
            "producto": {
                "referencia": producto[0],
                "peso": producto[1],
                "precio": producto[2]
            }
        }
    )


@router.post("/inventario/editar")
def guardar_edicion(
    request: Request,
    referencia: str = Form(...),
    peso: float = Form(...),
    precio: float = Form(...)
):

    if request.session.get("role") != "admin":
        return RedirectResponse("/admin", 303)

    conn = db()
    c = conn.cursor()

    c.execute("""
        UPDATE inventario
        SET peso_unitario_gr=?,
            precio_unitario=?
        WHERE referencia=?
    """, (peso, precio, referencia))

    conn.commit()
    conn.close()

    return RedirectResponse("/inventario", 303)


# ================= RESET INVENTARIO =================

@router.get("/inventario/reset")
def reset_inventario(request: Request):

    if request.session.get("role") != "admin":
        return RedirectResponse("/admin", 303)

    conn = db()
    c = conn.cursor()

    c.execute("DELETE FROM movimientos_inventario")
    c.execute("DELETE FROM inventario")

    conn.commit()
    conn.close()

    return RedirectResponse("/inventario", 303)

@router.post("/inventario/importar")
async def importar_inventario(
    request: Request,
    file: UploadFile = File(...)
):

    if request.session.get("role") != "admin":
        return RedirectResponse("/admin", 303)

    df = pd.read_excel(file.file)
    df.columns = df.columns.str.strip().str.lower()

    conn = db()
    c = conn.cursor()

    # Limpiar tablas
    c.execute("DELETE FROM movimientos_inventario")
    c.execute("DELETE FROM inventario")

    usuario = request.session.get("username")

    for _, row in df.iterrows():

        referencia = str(row.get("referencia", "")).strip()
        peso = float(row.get("peso unitario (gr)", 0))
        precio = float(row.get("precio unitario", 0))
        disponibles = int(row.get("disponibles", 0))

        if not referencia:
            continue

        # Insertar producto
        c.execute("""
            INSERT INTO inventario
            (referencia, peso_unitario_gr, cantidad_total, entregadas, total_disponibles, precio_unitario)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            referencia,
            peso,
            disponibles,   # cantidad_total
            0,             # entregadas
            disponibles,   # total_disponibles
            precio
        ))

        # Movimiento inicial automático
        if disponibles > 0:
            c.execute("""
                INSERT INTO movimientos_inventario
                (referencia, tipo, cantidad, usuario)
                VALUES (?, ?, ?, ?)
            """, (
                referencia,
                "INGRESO",
                disponibles,
                f"{usuario} (AJUSTE INICIAL)"
            ))

    conn.commit()
    conn.close()

    return RedirectResponse("/inventario", 303)

@router.post("/inventario/eliminar")
def eliminar_producto(
    request: Request,
    referencia: str = Form(...)
):

    if request.session.get("role") != "admin":
        return RedirectResponse("/admin", 303)

    conn = db()
    c = conn.cursor()

    # Borrar movimientos primero (por integridad)
    c.execute("DELETE FROM movimientos_inventario WHERE referencia=?", (referencia,))

    # Borrar producto
    c.execute("DELETE FROM inventario WHERE referencia=?", (referencia,))

    conn.commit()
    conn.close()

    return RedirectResponse("/inventario", 303)

@router.get("/api/kardex/{referencia:path}")
def api_kardex(referencia: str):

    conn = db()
    c = conn.cursor()

    movimientos = c.execute("""
        SELECT tipo, cantidad, usuario, fecha
        FROM movimientos_inventario
        WHERE referencia=?
        ORDER BY id ASC
    """, (referencia,)).fetchall()

    saldo = 0
    kardex = []

    for tipo, cantidad, usuario, fecha in movimientos:

        if tipo == "INGRESO":
            saldo += cantidad
        else:
            saldo -= cantidad

        kardex.append({
            "fecha": fecha,
            "tipo": tipo,
            "cantidad": cantidad,
            "usuario": usuario,
            "saldo": saldo
        })

    conn.close()

    return kardex

from pydantic import BaseModel

class Movimiento(BaseModel):
    referencia: str
    tipo: str
    cantidad: int


from fastapi import Form

@router.post("/api/movimiento")
def api_movimiento(
    referencia: str = Form(...),
    tipo: str = Form(...),
    cantidad: int = Form(...)
):

    conn = db()
    c = conn.cursor()

    c.execute("""
        INSERT INTO movimientos_inventario
        (referencia, tipo, cantidad, usuario)
        VALUES (?,?,?,?)
    """, (referencia, tipo, cantidad, "ANDROID"))

    conn.commit()
    conn.close()

    return {"status": "ok"}