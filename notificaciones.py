import logging
from datetime import datetime, timedelta
import zoneinfo
from database import db
from utils_wpp import enviar_whatsapp_background

logger = logging.getLogger(__name__)

def calcular_fecha_dia_habil_anterior() -> datetime.date:
    tz = zoneinfo.ZoneInfo('America/Bogota')
    hoy = datetime.now(tz).date()
    
    if hoy.weekday() == 0:  # Lunes
        return hoy - timedelta(days=3) # Viernes anterior
    else:
        return hoy - timedelta(days=1)

def obtener_operarios_sin_registro(fecha):
    conn = db()
    c = conn.cursor()
    try:
        c.execute("""
            SELECT o.id, o.nombre FROM operarios o
            WHERE o.activo = TRUE
            AND NOT EXISTS (
                SELECT 1 FROM registros_produccion r
                WHERE r.operario_id = o.id AND r.inicio::date = %s
            )
            ORDER BY o.nombre
        """, (fecha,))
        return [{'id': r[0], 'nombre': r[1]} for r in c.fetchall()]
    finally:
        conn.close()

def obtener_telefonos_jefe_tickets():
    conn = db()
    c = conn.cursor()
    try:
        c.execute("""
            SELECT telefono FROM users 
            WHERE role = 'jefe_tickets' 
            AND telefono IS NOT NULL AND telefono != ''
        """)
        return [r[0] for r in c.fetchall()]
    finally:
        conn.close()

def construir_mensaje_ausencias(fecha, operarios_sin_registro):
    if not operarios_sin_registro:
        return None
        
    fecha_str = fecha.strftime('%d/%m/%Y')
    
    lineas_operarios = [f"• {o['nombre']}" for o in operarios_sin_registro]
    texto_operarios = "\n".join(lineas_operarios)
    total = len(operarios_sin_registro)
    
    mensaje = (
        "⚠️ *Alerta de producción*\n"
        f"Fecha revisada: {fecha_str}\n\n"
        "Los siguientes operarios no registraron actividad:\n"
        f"{texto_operarios}\n\n"
        f"Total: {total}\n\n"
        "Por favor haz seguimiento con cada colaborador."
    )
    return mensaje

def notificar_ausencias_operarios():
    try:
        fecha = calcular_fecha_dia_habil_anterior()
        operarios = obtener_operarios_sin_registro(fecha)
        telefonos = obtener_telefonos_jefe_tickets()
        
        mensaje = construir_mensaje_ausencias(fecha, operarios)
        if mensaje and telefonos:
            for tel in telefonos:
                try:
                    enviar_whatsapp_background(tel, mensaje)
                except Exception as e:
                    logger.error(f"Error enviando whatsapp a {tel}: {e}")
                    
        return {"fecha": str(fecha), "operarios_sin_registro": len(operarios), "enviado": bool(mensaje and telefonos)}
    except Exception as e:
        logger.error(f"Error general en notificar_ausencias_operarios: {e}")
        return {"error": str(e)}
