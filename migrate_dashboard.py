import sys

with open("main.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

in_dashboard_section = False
dashboard_lines = []
main_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    if line.startswith("@app.get(\"/\", response_class=HTMLResponse)"):
        in_dashboard_section = True
    
    if in_dashboard_section:
        if line.startswith("# ================= CREACION DE ORDENES WEB ================="):
            in_dashboard_section = False
            main_lines.append(line)
        else:
            line = line.replace("@app.get", "@router.get")
            line = line.replace("return templates.TemplateResponse", "return request.app.state.templates.TemplateResponse")
            dashboard_lines.append(line)
    else:
        main_lines.append(line)
    i += 1

with open("main.py", "w", encoding="utf-8") as f:
    f.writelines(main_lines)

dashboard_imports = """from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from auth import require_admin
from database import db
from datetime import datetime
from routers.planificador import sincronizar_actividades_ordenes_abiertas

router = APIRouter()

"""

with open("routers/dashboard.py", "w", encoding="utf-8") as f:
    f.write(dashboard_imports)
    f.writelines(dashboard_lines)

print("Migrado a dashboard.py exitosamente")

