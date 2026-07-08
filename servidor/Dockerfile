FROM python:3.11-slim

# Evitar prompts interactivos y bytecode .pyc
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencias del sistema para opencv-headless, faiss, git (para gitpython)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 git && \
    rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar codigo fuente
COPY . .

# Crear directorios para datos persistentes (se montan como volumenes)
RUN mkdir -p /app/vectorstore_data /app/ml_models

# Migrar BD y arrancar gunicorn
# --timeout 120: las respuestas del LLM pueden tardar
# --workers 2: suficiente para uso moderado, bajo consumo de RAM
EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate --no-input && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --timeout 120 --workers 2"]
