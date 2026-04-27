from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from database import db
from collections import defaultdict
import math

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# ==============================
# 🔹 MODELO DE ACTIVIDAD
# ==============================

class Actividad:
    def __init__(self, id, nombre, tiempo, predecesoras=None):
        self.id = id
        self.nombre = nombre
        self.tiempo = tiempo
        self.predecesoras = predecesoras or []
        self.inicio = 0
        self.fin = 0


# ==============================
# 🔹 SIMULADOR (NUEVO MOTOR)
# ==============================

def simular_actividades(actividades):

    actividades_dict = {a.id: a for a in actividades}

    for act in actividades:

        if not act.predecesoras:
            act.inicio = 0
        else:
            act.inicio = max(
                actividades_dict[p].fin for p in act.predecesoras
            )

        act.fin = act.inicio + act.tiempo

    tiempo_total = max(a.fin for a in actividades)

    return tiempo_total, actividades


# ==============================
# 🔹 DEPENDENCIAS (CLAVE)
# ==============================

def obtener_predecesoras(nombre):

    mapa = {
        "Limpiar": [],
        "Avellanar": ["Limpiar"],
        "Poner": ["Limpiar"],
        "Encamisar": ["Limpiar"],
        "Asentar": ["Encamisar"],
        "Armar cilindro": ["Asentar"],
        "Cureña": ["Limpiar"],
        "Ensamble y pulido": ["Cureña"],
        "Resoldado": ["Ensamble y pulido"],
        "Guarda": ["Resoldado"],
        "Piñon": ["Limpiar"],
        "Cableado": ["Limpiar"],
        "Ensamble despulpadora": ["Armar cilindro", "Guarda", "Piñon", "Cableado"],
        "enhuacalar": ["Ensamble despulpadora"]
    }

    for key in mapa:
        if key.lower() in nombre.lower():
            return mapa[key]

    return []


# ==============================
# 🔹 GET
# ==============================

@router.get("/planificador", response_class=HTMLResponse)
async def planificador(request: Request, maquina_id: int | None = None):

    conn = db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, nombre FROM maquinas")
    maquinas = cursor.fetchall()

    if maquina_id is None and maquinas:
        maquina_id = maquinas[0][0]

    cursor.execute("SELECT id, nombre FROM operarios")
    operarios = cursor.fetchall()

    cursor.execute("""
        SELECT
            a.id,
            a.nombre,
            AVG(ea.unidades_por_hora)
        FROM actividades a
        LEFT JOIN estandares_actividad ea ON ea.actividad_id = a.id
        JOIN procesos p ON a.proceso_id = p.id
        WHERE p.maquina_id = ?
        GROUP BY a.id, a.nombre
    """, (maquina_id,))

    actividades = cursor.fetchall()

    return templates.TemplateResponse(
        "planificador.html",
        {
            "request": request,
            "actividades": actividades,
            "maquinas": maquinas,
            "operarios": operarios,
            "maquina_id": maquina_id,
            "resultado": None,
            "cronograma": [],
            "tabla_procesos": [],
            "cuello_botella": None
        }
    )


# ==============================
# 🔹 POST (SIMULACIÓN REAL)
# ==============================

@router.post("/calcular-produccion", response_class=HTMLResponse)
async def calcular_produccion(
    request: Request,
    cantidad: int = Form(...),
    maquina_id: int = Form(...)
):

    form = await request.form()

    conn = db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, nombre FROM maquinas")
    maquinas = cursor.fetchall()

    cursor.execute("SELECT id, nombre FROM operarios")
    operarios = cursor.fetchall()

    cursor.execute("""
        SELECT
            a.id,
            a.nombre,
            AVG(ea.unidades_por_hora)
        FROM actividades a
        LEFT JOIN estandares_actividad ea ON ea.actividad_id = a.id
        JOIN procesos p ON a.proceso_id = p.id
        WHERE p.maquina_id = ?
        GROUP BY a.id, a.nombre
    """, (maquina_id,))

    data = cursor.fetchall()

    # ==========================
    # 🔥 CREAR ACTIVIDADES REALES
    # ==========================

    actividades_sim = []
    nombre_to_id = {}

    for act_id, nombre, unidades_hora in data:

        operarios_asignados = form.getlist(f"actividad_{act_id}")
        num_operarios = len(operarios_asignados)

        if unidades_hora and num_operarios:
            capacidad = unidades_hora * num_operarios
            tiempo = cantidad / capacidad
        else:
            tiempo = 0

        actividad = Actividad(act_id, nombre, tiempo)
        actividades_sim.append(actividad)
        nombre_to_id[nombre] = act_id

    # ==========================
    # 🔥 ASIGNAR DEPENDENCIAS
    # ==========================

    for act in actividades_sim:

        nombres_pred = obtener_predecesoras(act.nombre)

        act.predecesoras = [
            nombre_to_id[n]
            for n in nombre_to_id
            if any(p.lower() in n.lower() for p in nombres_pred)
        ]

    # ==========================
    # 🔥 SIMULAR
    # ==========================

    tiempo_total, resultado_acts = simular_actividades(actividades_sim)

    # ==========================
    # 🔥 CRONOGRAMA
    # ==========================

    cronograma = [
        {
            "actividad": a.nombre,
            "inicio": round(a.inicio, 2),
            "fin": round(a.fin, 2)
        }
        for a in resultado_acts
    ]

    # ==========================
    # 🔥 CUELLO DE BOTELLA
    # ==========================

    cuello = max(resultado_acts, key=lambda x: x.tiempo)

    horas_dia = 530 / 60

    dias = tiempo_total / horas_dia if tiempo_total else 0
    produccion_dia = cantidad / dias if dias else 0

    resultado = f"""
Producción diaria: <b>{round(produccion_dia,2)}</b> máquinas/día
<br><br>
Tiempo total del flujo: <b>{round(tiempo_total,2)}</b> horas
<br><br>
Tiempo estimado: <b>{math.ceil(dias)}</b> días
<br><br>
🔴 Cuello de botella: <b>{cuello.nombre}</b>
<br>
Tiempo: <b>{round(cuello.tiempo,2)} horas</b>
"""

    return templates.TemplateResponse(
        "planificador.html",
        {
            "request": request,
            "resultado": resultado,
            "cronograma": cronograma,
            "tabla_procesos": [],
            "cuello_botella": cuello.nombre,
            "maquinas": maquinas,
            "operarios": operarios,
            "maquina_id": maquina_id,
            "actividades": data
        }
    )