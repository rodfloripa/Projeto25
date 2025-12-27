import os
import json
import sqlite3
import openai
from flask import Flask, request, jsonify
from pymilvus import connections, FieldSchema, CollectionSchema, DataType, Collection,utility
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
from flask_cors import CORS

# Carrega variáveis de um arquivo .env se existir (útil para teste local)
load_dotenv()

app = Flask(__name__)
CORS(app) # Libera para todos

# --- Configurações e Modelos ---
# O Heroku fornece a porta via variável de ambiente $PORT
PORT = int(os.getenv("PORT", 5000))
openai.api_key = os.getenv("OPENAI_API_KEY")
MILVUS_URI = os.getenv("MILVUS_URI")  # URL do Zilliz Cloud
MILVUS_TOKEN = os.getenv("MILVUS_TOKEN") # Token/Password do Zilliz

# Modelo de Embeddings (Otimizado para 384 dimensões)
model = SentenceTransformer('all-MiniLM-L6-v2')

# --- Conexões ---

# 1. Conexão Milvus (Zilliz Cloud)
connections.connect(
    alias="default",
    uri=MILVUS_URI,
    token=MILVUS_TOKEN,
    secure=True # Obrigatório para Zilliz Cloud
)

# 2. Conexão SQLite (Histórico)
def get_db_connection():
    # Nota: No Heroku, este arquivo é deletado a cada deploy/restart (sistema efêmero)
    conn = sqlite3.connect('conversas.db', check_same_thread=False)
    return conn

# Inicializar tabela SQLite
db = get_db_connection()
db.execute('''CREATE TABLE IF NOT EXISTS conversas 
              (id INTEGER PRIMARY KEY AUTOINCREMENT, pergunta TEXT, resposta TEXT)''')
db.commit()

# --- Configuração do Schema Milvus (Ajustado para o novo modelo) ---
collection_name = "sac_collection_v2" # Sugestão: v2 devido à mudança de dimensão
dim = 384 # Dimensão correta para o all-MiniLM-L6-v2

fields = [
    FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
    FieldSchema(name="conteudo", dtype=DataType.VARCHAR, max_length=4096),
    FieldSchema(name="fonte", dtype=DataType.VARCHAR, max_length=500),
    FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=dim)
]

schema = CollectionSchema(fields, description="Vetorização de documentos com MiniLM")

# Cria ou carrega a coleção

if not utility.has_collection(collection_name):
    print(f"Coleção {collection_name} não encontrada. Criando...")
    collection = Collection(name=collection_name, schema=schema)
    index_params = {
        "index_type": "IVF_FLAT",
        "params": {"nlist": 1024},
        "metric_type": "L2"
    }
    collection.create_index(field_name="vector", index_params=index_params)
else:
    collection = Collection(name=collection_name)

collection.load()

# --- Lógica de Inicialização de Dados ---

def popular_banco_se_vazio():
    # Verifica se a coleção está vazia (usando num_entities após flush ou count)
    if collection.num_entities == 0:
        print("Populando banco de dados vetorial...")
        try:
            if os.path.exists('dados-sac.md'):
                with open('dados-sac.md', 'r', encoding='utf-8') as f:
                    texto_completo = f.read()

                # --- Configuração do Chunking ---
                tamanho_chunk = 500  
                sobreposicao = 100    
                
                chunks = []
                for i in range(0, len(texto_completo), tamanho_chunk - sobreposicao):
                    chunk = texto_completo[i : i + tamanho_chunk].strip()
                    if chunk:
                        chunks.append(chunk)

                if chunks:
                    fontes = ["dados-sac.md"] * len(chunks)
                    # Gerar vetores (dimensão 384)
                    vetores = model.encode(chunks).tolist()
                    
                    dados = [
                        chunks, # campo: conteudo
                        fontes, # campo: fonte
                        vetores # campo: vector
                    ]
                    
                    collection.insert(dados)
                    collection.flush()
                    print(f"Sucesso! {len(chunks)} trechos inseridos.")
            else:
                print("Arquivo dados-sac.md não encontrado para o seed inicial.")

        except Exception as e:
            print(f"Erro ao popular banco: {str(e)}")

popular_banco_se_vazio()

# --- Funções Auxiliares ---

def responder_sac(pergunta_usuario):
    # 1. Gerar embedding da pergunta
    search_vector = [model.encode(pergunta_usuario).tolist()]
    
    # 2. Busca vetorial
    search_params = {"metric_type": "L2", "params": {"nprobe": 10}}
    results = collection.search(
        data=search_vector, 
        anns_field="vector", 
        param=search_params, 
        limit=3, 
        output_fields=["conteudo"]
    )
    
    # 3. Extrair contexto
    contexto_extraido = ""
    if results and len(results[0]) > 0:
        for hit in results[0]:
            # Limiar de distância (ajustável)
            if hit.distance < 1.5: 
                contexto_extraido += hit.entity.get("conteudo") + "\n\n"

    # 4. Prompt para OpenAI
    if contexto_extraido:
        prompt_final = (
            f"Você é um assistente de SAC profissional. Use o contexto abaixo para responder.\n\n"
            f"Contexto:\n{contexto_extraido}\n"
            f"Pergunta: {pergunta_usuario}\n\n"
            f"Responda baseando-se no contexto."
        )
    else:
        prompt_final = f"Você é um assistente de SAC. Responda da melhor forma: {pergunta_usuario}"
    
    # 5. Chamar a OpenAI (ChatCompletion API)
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Você é um assistente de SAC prestativo."},
                {"role": "user", "content": prompt_final}
            ],
            max_tokens=500,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Erro ao processar com IA: {str(e)}"

# --- Rotas da API ---

@app.route('/sac', methods=['POST'])
def sac():
    data = request.get_json()
    if not data or "pergunta" not in data:
        return jsonify({"error": "Campo 'pergunta' é obrigatório"}), 400
    
    pergunta = data["pergunta"]
    resposta = responder_sac(pergunta)
    
    # Salvar no SQLite (Histórico temporário)
    try:
        cursor = db.cursor()
        cursor.execute('INSERT INTO conversas (pergunta, resposta) VALUES (?, ?)', (pergunta, resposta))
        db.commit()
    except:
        pass

    return jsonify({"pergunta": pergunta, "resposta": resposta})



if __name__ == '__main__':
    # O Heroku usa gunicorn, mas para teste local:
    app.run(host="0.0.0.0", port=PORT)
