FROM python:3.11-slim

# Instalar dependencias del sistema requeridas para pg_dump
RUN apt-get update && apt-get install -y postgresql-client && rm -rf /var/lib/apt/lists/*

# Establecer directorio de trabajo
WORKDIR /app

# Copiar e instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el codigo fuente
COPY . .

# Iniciar la aplicacion usando el script de python seguro
CMD ["python", "start.py"]
