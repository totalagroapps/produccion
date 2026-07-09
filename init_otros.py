import os
from database import db

def main():
    conn = db()
    c = conn.cursor()
    
    # 1. Check or Create Machine
    c.execute("SELECT id FROM maquinas WHERE UPPER(nombre) = 'OTROS'")
    row = c.fetchone()
    if row:
        maquina_id = row[0]
        print(f"Maquina 'OTROS' exists with ID: {maquina_id}")
    else:
        c.execute("INSERT INTO maquinas (nombre) VALUES ('OTROS') RETURNING id")
        maquina_id = c.fetchone()[0]
        print(f"Created Maquina 'OTROS' with ID: {maquina_id}")

    # 2. Check or Create Process under Machine 'OTROS'
    c.execute("SELECT id FROM procesos WHERE UPPER(nombre) = 'OTROS' AND maquina_id = %s", (maquina_id,))
    row = c.fetchone()
    if row:
        proceso_id = row[0]
        print(f"Proceso 'OTROS' exists with ID: {proceso_id}")
    else:
        c.execute("INSERT INTO procesos (maquina_id, nombre) VALUES (%s, 'OTROS') RETURNING id", (maquina_id,))
        proceso_id = c.fetchone()[0]
        print(f"Created Proceso 'OTROS' with ID: {proceso_id}")
        
    # 3. Check or Create an Open Order linked to Machine 'OTROS'
    c.execute("SELECT id FROM ordenes WHERE maquina_id = %s AND estado != 'CERRADA'", (maquina_id,))
    row = c.fetchone()
    if row:
        orden_id = row[0]
        print(f"Open Order for 'OTROS' exists with ID: {orden_id}")
    else:
        c.execute("INSERT INTO ordenes (maquina_id, cantidad, estado, porcentaje) VALUES (%s, 99999, 'EN PROCESO', 0) RETURNING id", (maquina_id,))
        orden_id = c.fetchone()[0]
        print(f"Created Open Order for 'OTROS' with ID: {orden_id}")

    conn.commit()
    conn.close()
    print("Done!")

if __name__ == '__main__':
    main()
