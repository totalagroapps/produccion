from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
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
                COALESCE(AVG(ea.unidades_por_hora), 0)
            FROM actividades a
            JOIN procesos p ON a.proceso_id = p.id
            LEFT JOIN estandares_actividad ea ON ea.actividad_id = a.id
            WHERE p.maquina_id = %s
            GROUP BY p.id, p.nombre, a.id, a.nombre
            ORDER BY p.id, a.id
        """, (maquina_id,))

        rows = cursor.fetchall() or []
        normalizados = [
            {
                "id": row[2],
                "nombre": row[3],
                "normalizado": normalizar(row[3]),
            }
            for row in rows
        ]

        for proceso_id, proceso, actividad_id, actividad, unidades_hora in rows:
            pred_patrones = nombres_predecesores(actividad)
            pred_ids = []
            pred_nombres = []

            for patron in pred_patrones:
                for item in normalizados:
                    if item["id"] == actividad_id:
                        continue

                    if patron in item["normalizado"]:
                        pred_ids.append(item["id"])
                        pred_nombres.append(item["nombre"])

            actividades.append({
                "proceso_id": proceso_id,
                "proceso": proceso,
                "id": actividad_id,
                "nombre": actividad,
                "unidades_hora": float(unidades_hora or 0),
                "predecesoras": pred_ids,
                "predecesoras_nombres": pred_nombres,
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
