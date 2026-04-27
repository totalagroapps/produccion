from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()

templates = Jinja2Templates(directory="templates")

@router.get("/configuracion", response_class=HTMLResponse)
def panel_admin(request: Request):
    return templates.TemplateResponse(
        request=request, name="admin.html", context={"request": request}
    )