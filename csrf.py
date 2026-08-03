from fastapi import Request, HTTPException
import secrets

async def verify_csrf(request: Request):
    if "csrf_token" not in request.session:
        request.session["csrf_token"] = secrets.token_hex(32)
        
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return
        
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return
        
    if request.url.path == "/android/login":
        return
        
    token = request.headers.get("x-csrf-token")
    if not token:
        content_type = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            try:
                form = await request.form()
                token_field = form.get("csrf_token")
                if isinstance(token_field, str):
                    token = token_field
            except Exception:
                pass
                
    session_token = request.session.get("csrf_token")
    if not session_token or not token or not secrets.compare_digest(session_token, token):
        raise HTTPException(status_code=403, detail="CSRF token invalido o faltante")
