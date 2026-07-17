import os
import subprocess
import gzip
import boto3
from datetime import datetime, timedelta
from dotenv import load_dotenv
import psycopg2
from urllib.parse import urlparse

# Cargar variables de entorno
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
S3_ENDPOINT = os.getenv("S3_ENDPOINT")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

def init_db():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS backups_log (
            id SERIAL PRIMARY KEY,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            tipo VARCHAR(50),
            nombre_archivo VARCHAR(255),
            tamano_bytes BIGINT,
            estado VARCHAR(50),
            error TEXT
        );
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error inicializando tabla backups_log: {e}")

def log_backup(tipo, nombre_archivo, tamano_bytes, estado, error_msg=""):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()
        c.execute("""
            INSERT INTO backups_log (tipo, nombre_archivo, tamano_bytes, estado, error)
            VALUES (%s, %s, %s, %s, %s)
        """, (tipo, nombre_archivo, tamano_bytes, estado, error_msg))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error loggeando backup: {e}")

def rotar_backups(s3_client, bucket_name):
    """
    Conserva los últimos 7 días y los backups semanales (domingos) hasta 4 semanas atrás.
    Borra el resto.
    """
    try:
        response = s3_client.list_objects_v2(Bucket=bucket_name)
        if 'Contents' not in response:
            return

        archivos = []
        for obj in response['Contents']:
            if obj['Key'].endswith('.sql.gz'):
                archivos.append(obj)
        
        # Ordenar de más nuevo a más viejo
        archivos.sort(key=lambda x: x['LastModified'], reverse=True)
        ahora = datetime.now(tz=archivos[0]['LastModified'].tzinfo) if archivos else datetime.now()

        for obj in archivos:
            fecha_obj = obj['LastModified']
            dias_antiguedad = (ahora - fecha_obj).days
            es_domingo = fecha_obj.weekday() == 6
            
            conservar = False
            if dias_antiguedad <= 7:
                conservar = True # Mantener últimos 7 días
            elif es_domingo and dias_antiguedad <= 28:
                conservar = True # Mantener 4 domingos
                
            if not conservar:
                s3_client.delete_object(Bucket=bucket_name, Key=obj['Key'])
                print(f"Backup rotado/eliminado: {obj['Key']}")
    except Exception as e:
        print(f"Error rotando backups: {e}")


def ejecutar_backup_completo(tipo="AUTOMATICO"):
    print(f"Iniciando backup {tipo}...")
    init_db()
    
    if not DATABASE_URL:
        log_backup(tipo, "", 0, "FALLO", "Falta DATABASE_URL")
        return {"estado": "error", "mensaje": "Falta DATABASE_URL"}
        
    if not all([S3_ENDPOINT, S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET_NAME]):
        log_backup(tipo, "", 0, "FALLO", "Faltan credenciales de S3")
        return {"estado": "error", "mensaje": "Faltan credenciales de S3"}

    # Nombres de archivo
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    db_name = urlparse(DATABASE_URL).path[1:]
    filename_sql = f"{db_name}_{timestamp}.sql"
    filename_gz = f"{filename_sql}.gz"
    filepath_gz = f"/tmp/{filename_gz}"

    try:
        # Ejecutar pg_dump
        print("Ejecutando pg_dump...")
        with gzip.open(filepath_gz, 'wb') as f_out:
            process = subprocess.Popen(
                ['pg_dump', DATABASE_URL],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            # Leer stdout y escribir en archivo gzip
            while True:
                chunk = process.stdout.read(8192)
                if not chunk:
                    break
                f_out.write(chunk)
                
        process.wait()
        
        if process.returncode != 0:
            error_output = process.stderr.read().decode('utf-8')
            raise Exception(f"pg_dump falló con código {process.returncode}: {error_output}")

        tamano_bytes = os.path.getsize(filepath_gz)
        
        # Subir a S3
        print("Subiendo a S3...")
        s3 = boto3.client('s3',
            endpoint_url=S3_ENDPOINT,
            aws_access_key_id=S3_ACCESS_KEY,
            aws_secret_access_key=S3_SECRET_KEY
        )
        s3.upload_file(filepath_gz, S3_BUCKET_NAME, filename_gz)
        
        # Loggear exito
        log_backup(tipo, filename_gz, tamano_bytes, "EXITO")
        
        # Rotar
        rotar_backups(s3, S3_BUCKET_NAME)

    except Exception as e:
        print(f"Fallo el backup: {e}")
        log_backup(tipo, filename_gz, 0, "FALLO", str(e))
        return {"estado": "error", "mensaje": str(e)}
        
    finally:
        # Limpiar archivo temporal
        if os.path.exists(filepath_gz):
            os.remove(filepath_gz)

    print(f"Backup {tipo} finalizado con éxito.")
    return {"estado": "ok", "mensaje": "Backup subido exitosamente", "archivo": filename_gz}

if __name__ == "__main__":
    # Permite ejecutarlo manualmente desde consola
    ejecutar_backup_completo("MANUAL")
