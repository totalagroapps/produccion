from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from database import db
import pandas as pd

router = APIRouter()


# ================= PANEL ADMINISTRATIVO =================

@router.get("/admin_tools", response_class=HTMLResponse)
def admin_tools_panel(request: Request):

    if request.session.get("role") != "admin":
        return RedirectResponse("/admin", 303)

    return request.app.state.templates.TemplateResponse(
        "admin_tools_panel.html",
        {"request": request}
    )


# ================= RESET METRICAS =================

@router.get("/admin_tools/reset_metricas")
def reset_metricas(request: Request):

    if request.session.get("role") != "admin":
        return RedirectResponse("/admin", 303)

    conn = db()
    c = conn.cursor()

    c.execute("DELETE FROM registros_produccion")
    c.execute("DELETE FROM bonos")
    c.execute("UPDATE ordenes SET porcentaje=0, estado='ABIERTA', cerrado_en=NULL")
    c.execute("UPDATE orden_actividades SET cantidad_realizada=0")

    conn.commit()
    conn.close()

    return RedirectResponse("/admin_tools", 303)


# ================= BORRAR REGISTROS =================

@router.get("/admin_tools/borrar_registros")
def borrar_registros(request: Request):

    if request.session.get("role") != "admin":
        return RedirectResponse("/admin", 303)

    conn = db()
    c = conn.cursor()

    c.execute("DELETE FROM registros_produccion")

    conn.commit()
    conn.close()

    return RedirectResponse("/admin_tools", 303)


# ================= CARGAR ESTANDARES =================

@router.get("/admin_tools/cargar_estandares_excel")
def cargar_estandares_excel(request: Request):

    if request.session.get("role") != "admin":
        return RedirectResponse("/admin", 303)

    conn = db()
    c = conn.cursor()

    ruta = "excel/estandares.xlsx"
    df = pd.read_excel(ruta)

    c.execute("DELETE FROM estandares_actividad")

    for _, row in df.iterrows():

        actividad_id = int(row["actividad_id"])
        unidades = float(row["unidades_por_hora"])
        costo = float(row["costo_mo_unidad"])

        c.execute("""
            INSERT INTO estandares_actividad
            (actividad_id, unidades_por_hora, costo_mo_unidad, costo_mo_hora)
            VALUES (?, ?, ?, 0)
        """, (actividad_id, unidades, costo))

    conn.commit()
    conn.close()

    return RedirectResponse("/admin_tools", 303)

@router.post("/maquinas")
def crear_maquina(nombre: str):
    conn = db()
    c = conn.cursor()

    c.execute(
        "INSERT INTO maquinas (nombre) VALUES (?)",
        (nombre,)
    )

    conn.commit()
    conn.close()

    return {"mensaje": "maquina creada"}

@router.put("/maquinas/{id}")
def editar_maquina(id: int, nombre: str):
    conn = db()
    c = conn.cursor()

    c.execute(
        "UPDATE maquinas SET nombre=? WHERE id=?",
        (nombre, id)
    )

    conn.commit()
    conn.close()

    return {"mensaje": "maquina actualizada"}

@router.delete("/maquinas/{id}")
def eliminar_maquina(id: int):
    conn = db()
    c = conn.cursor()

    c.execute(
        "DELETE FROM maquinas WHERE id=?",
        (id,)
    )

    conn.commit()
    conn.close()

    return {"mensaje": "maquina eliminada"}

