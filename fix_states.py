
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

try:
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    c = conn.cursor()
    c.execute("UPDATE tickets SET estado = 'EN_PROGRESO' WHERE estado = 'EN PROGRESO'")
    c.execute("UPDATE tickets SET estado = 'CERRADO' WHERE estado = 'COMPLETADO'")
    conn.commit()
    conn.close()
    print('DB states standardized.')
except Exception as e:
    print('DB Error:', e)

