import sys
from database import db

def run():
    conn = db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS actividad_dependencias (
            actividad_id INTEGER NOT NULL,
            predecesora_id INTEGER NOT NULL,
            PRIMARY KEY (actividad_id, predecesora_id),
            CONSTRAINT fk_act_dep_act FOREIGN KEY (actividad_id) REFERENCES actividades(id) ON DELETE CASCADE,
            CONSTRAINT fk_act_dep_pred FOREIGN KEY (predecesora_id) REFERENCES actividades(id) ON DELETE CASCADE
        );
        """)
        conn.commit()
        print("Tabla actividad_dependencias creada exitosamente.")
    except Exception as e:
        conn.rollback()
        print("Error:", e)
    finally:
        conn.close()

if __name__ == '__main__':
    run()
