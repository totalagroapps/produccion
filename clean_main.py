import sys

with open("main.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
skip = False
for line in lines:
    if line.startswith("@app.get(`"/`", response_class=HTMLResponse)") or \
       line.startswith("@app.get(`"/panel`", response_class=HTMLResponse)") or \
       line.startswith("@app.get(`"/metricas_operarios`", response_class=HTMLResponse)") or \
       line.startswith("@app.get(`"/kpi`", response_class=HTMLResponse)") or \
       line.startswith("@app.get(`"/inicio_operario`", response_class=HTMLResponse)"):
        skip = True
    
    if skip and line.strip() == "" and len(new_lines) > 0 and new_lines[-1].strip() == "":
        # Found the end of a function block (two blank lines usually separate them, or we can just look for the next @app)
        pass

    # A better way to skip functions:
    if skip and line.startswith("@app") and not (
        line.startswith("@app.get(`"/`", response_class=HTMLResponse)") or \
        line.startswith("@app.get(`"/panel`", response_class=HTMLResponse)") or \
        line.startswith("@app.get(`"/metricas_operarios`", response_class=HTMLResponse)") or \
        line.startswith("@app.get(`"/kpi`", response_class=HTMLResponse)") or \
        line.startswith("@app.get(`"/inicio_operario`", response_class=HTMLResponse)")
    ):
        skip = False

    if not skip:
        new_lines.append(line)

with open("main.py", "w", encoding="utf-8") as f:
    f.writelines(new_lines)

