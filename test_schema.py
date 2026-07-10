from database import db
c = db().cursor()
c.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='actividades'")
print("ACTIVIDADES:", c.fetchall())

c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
print("TABLES:", c.fetchall())
