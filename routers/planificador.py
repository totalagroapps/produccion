from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from database import db
import unicodedata

router = APIRouter()
templates = Jinja2Templates(directory="templates")


DEPENDENCIAS = [
    ("limpiar", []),
    ("avellanar", ["limpiar"]),
    ("poner", ["limpiar"]),
    ("encamisar", ["limpiar"]),
    ("asentar", ["encamisar"]),
    ("armar cilindro", ["asentar"]),
    ("curena", ["limpiar"]),
    ("ensamble y pulido", ["curena"]),
    ("resoldado", ["ensamble y pulido"]),
    ("guarda", ["resoldado"]),
    ("pinon", ["limpiar"]),
    ("cableado", ["limpiar"]),
    ("ensamble despulpadora", ["armar cilindro", "guarda", "pinon", "cableado"]),
    ("enhuacalar", ["ensamble despulpadora"]),
]


def normalizar(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", texto or "")
    sin_acentos = "".join(c for c in sin_acentos if not unicodedata.combining(c))
    return sin_acentos.lower().strip()


def nombres_predecesores(nombre: str) -> list[str]:
    nombre_normalizado = normalizar(nombre)

    for patron, predecesores in DEPENDENCIAS:
        if patron in nombre_normalizado:
            return predecesores

    return []


def cargar_datos_planificador(maquina_id: int | None):
    conn = db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, nombre FROM maquinas ORDER BY nombre")
    maquinas = cursor.fetchall() or []

    if maquina_id is None and maquinas:
        maquina_id = maquinas[0][0]

    cursor.execute("SELECT id, nombre FROM operarios ORDER BY nombre")
    operarios = cursor.fetchall() or []

    actividades = []

    if maquina_id:
        cursor.execute("""
            SELECT
                p.id,
                p.nombre,
                a.id,
                a.nombre,
                COALESCE(AVG(ea.unidades_por_hora), 0),
                ARRAY_AGG(ad.predecesora_id) FILTER (WHERE ad.predecesora_id IS NOT NULL),
                ARRAY_AGG(ap.nombre) FILTER (WHERE ad.predecesora_id IS NOT NULL)
            FROM actividades a
            JOIN procesos p ON a.proceso_id = p.id
            LEFT JOIN estandares_actividad ea ON ea.actividad_id = a.id
            LEFT JOIN actividad_dependencias ad ON ad.actividad_id = a.id
            LEFT JOIN actividades ap ON ap.id = ad.predecesora_id
            WHERE p.maquina_id = %s
            GROUP BY p.id, p.nombre, a.id, a.nombre
            ORDER BY p.id, a.id
        """, (maquina_id,))

        rows = cursor.fetchall() or []

        for row in rows:
            actividades.append({
                "proceso_id": row[0],
                "proceso": row[1],
                "id": row[2],
                "nombre": row[3],
                "unidades_hora": float(row[4] or 0),
                "predecesoras": row[5] or [],
                "predecesoras_nombres": row[6] or [],
            })

    conn.close()

    return maquinas, operarios, actividades, maquina_id


@router.get("/planificador", response_class=HTMLResponse)
async def planificador(request: Request, maquina_id: int | None = None):
    maquinas, operarios, actividades, maquina_id = cargar_datos_planificador(maquina_id)

    return templates.TemplateResponse(
        request=request,
        name="planificador.html",
        context={
            "request": request,
            "maquinas": maquinas,
            "operarios": operarios,
            "maquina_id": maquina_id,
            "actividades": actividades,
            "actividades_json": actividades,
            "operarios_json": [
                {"id": op[0], "nombre": op[1]}
                for op in operarios
            ],
        },
    )


@router.post("/calcular-produccion", response_class=HTMLResponse)
async def calcular_produccion(
    maquina_id: int = Form(...),
):
    return RedirectResponse(f"/planificador?maquina_id={maquina_id}", status_code=303)


@router.post("/api/planificador/dependencia/add")
async def add_dependencia(actividad_id: int = Form(...), predecesora_id: int = Form(...)):
    conn = db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO actividad_dependencias (actividad_id, predecesora_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (actividad_id, predecesora_id))
        conn.commit()
    finally:
        conn.close()
    return JSONResponse({"status": "ok"})

@router.post("/api/planificador/dependencia/remove")
async def remove_dependencia(actividad_id: int = Form(...), predecesora_id: int = Form(...)):
    conn = db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM actividad_dependencias WHERE actividad_id = %s AND predecesora_id = %s", (actividad_id, predecesora_id))
        conn.commit()
    finally:
        conn.close()
    return JSONResponse({"status": "ok"})

@router.get("/planificador/setup_db")
async def setup_db():
    conn = db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS actividad_dependencias (
            actividad_id INTEGER NOT NULL,
            predecesora_id INTEGER NOT NULL,
            PRIMARY KEY (actividad_id, predecesora_id),
            CONSTRAINT fk_act_dep_act FOREIGN KEY (actividad_id) REFERENCES actividades(id) ON DELETE CASCADE,
            CONSTRAINT fk_act_dep_pred FOREIGN KEY (predecesora_id) REFERENCES actividades(id) ON DELETE CASCADE
        );
        """)
        
        cursor.execute("SELECT id, nombre FROM actividades")
        todas = cursor.fetchall() or []
        normalizados = [{"id": r[0], "nombre": r[1], "normalizado": normalizar(r[1])} for r in todas]
        
        for item in normalizados:
            act_id = item["id"]
            patrones = nombres_predecesores(item["nombre"])
            for patron in patrones:
                for pred in normalizados:
                    if pred["id"] != act_id and patron in pred["normalizado"]:
                        cursor.execute(
                            "INSERT INTO actividad_dependencias (actividad_id, predecesora_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                            (act_id, pred["id"])
                        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        return HTMLResponse(f"Error: {e}")
    finally:
        conn.close()
        
    return RedirectResponse("/planificador", status_code=303)
