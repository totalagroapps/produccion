import sqlite3

conn = sqlite3.connect("produccion.db")
c = conn.cursor()

# MAQUINAS
c.execute("INSERT INTO maquinas VALUES (NULL,'Picapasto')")
c.execute("INSERT INTO maquinas VALUES (NULL,'Chipeadora')")
c.execute("INSERT INTO maquinas VALUES (NULL,'Despulpadora')")

# PROCESOS
c.execute("INSERT INTO procesos VALUES (NULL,1,'Corte')")
c.execute("INSERT INTO procesos VALUES (NULL,1,'Triturado')")
c.execute("INSERT INTO procesos VALUES (NULL,2,'Astillado')")
c.execute("INSERT INTO procesos VALUES (NULL,3,'Limpieza')")

conn.commit()
conn.close()

print("MAQUINAS Y PROCESOS CARGADOS")
