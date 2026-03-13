@router.get("/materiales_maquinas", response_class=HTMLResponse)
def materiales_maquinas(request: Request):

    conn = db()
    c = conn.cursor()

    maquinas = c.execute("""
        SELECT id, nombre
        FROM maquinas
        ORDER BY nombre
    """).fetchall()

    conn.close()

    return request.app.state.templates.TemplateResponse(
        "materiales_maquinas.html",
        {
            "request": request,
            "maquinas": maquinas
        }
    )