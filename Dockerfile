# 1. Imagem base leve oficial do Python
FROM python:3.9-slim

# 2. Instalação de dependências do sistema de forma ultra-otimizada
# O --no-install-recommends evita pacotes "sugestões" que não são essenciais
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 3. Definir diretório de trabalho
WORKDIR /app

# 4. Forçar instalação do PyTorch para CPU (Redução de ~6GB)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# 5. Copiar e instalar requisitos do Python
COPY Requirements.txt .
RUN pip install --no-cache-dir -r Requirements.txt

# 6. Pre-bake do Modelo: Baixa o modelo durante o build para o app subir rápido
# Usando o modelo solicitado de 384 dimensões
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# 7. Copiar o restante do código (O .dockerignore vai impedir a cópia da venv local)
COPY . .

# 8. Comando de inicialização configurado para a porta dinâmica do Heroku
# 'main:app' aponta para seu arquivo main.py e a instância Flask 'app'
CMD gunicorn --bind 0.0.0.0:$PORT main:app
