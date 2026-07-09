import os
import requests
import threading

def enviar_whatsapp_background(telefono: str, mensaje: str):
    if not telefono: return
    # Limpiar teléfono
    telefono = telefono.replace("+", "").replace(" ", "").strip()
    if not telefono: return
    
    # Proveedor 1: UltraMsg
    ULTRAMSG_TOKEN = os.getenv("ULTRAMSG_TOKEN", "")
    ULTRAMSG_INSTANCE = os.getenv("ULTRAMSG_INSTANCE", "")
    
    # Proveedor 2: CallMeBot
    # Soporte para múltiples jefes: Busca primero la llave específica del teléfono, si no, usa la global.
    CALLMEBOT_APIKEY = os.getenv(f"CALLMEBOT_APIKEY_{telefono}") or os.getenv("CALLMEBOT_APIKEY", "")
    
    try:
        if ULTRAMSG_TOKEN and ULTRAMSG_INSTANCE:
            url = f"https://api.ultramsg.com/{ULTRAMSG_INSTANCE}/messages/chat"
            payload = {
                "token": ULTRAMSG_TOKEN,
                "to": telefono,
                "body": mensaje
            }
            requests.post(url, data=payload, timeout=10)
        elif CALLMEBOT_APIKEY:
            url = f"https://api.callmebot.com/whatsapp.php"
            params = {
                "phone": telefono,
                "text": mensaje,
                "apikey": CALLMEBOT_APIKEY
            }
            requests.get(url, params=params, timeout=10)
        else:
            print(f"WHATSAPP MOCK (Falta configurar API en variables de entorno): To {telefono} -> {mensaje}")
    except Exception as e:
        print(f"Error enviando WhatsApp a {telefono}: {e}")

def notificar_ticket_asignado(telefono: str, consecutivo: str, titulo: str):
    msg = f"Hola, se te ha asignado un nuevo ticket en el Sistema de Produccion.\n\n*Ticket:* {consecutivo}\n*Titulo:* {titulo}\n\nPor favor, ingresa al sistema para revisar los detalles."
    threading.Thread(target=enviar_whatsapp_background, args=(telefono, msg)).start()
