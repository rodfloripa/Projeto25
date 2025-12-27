# Aprenda sobre doenças com RodMed
<p align="justify">
  Neste projeto foi feita a raspagem de dados do  <a href="https://www.gov.br/saude/pt-br/assuntos/saude-de-a-a-z">site de doenças</a>  do Ministério da Saúde.Usando LLM criei uma RAG que 
  reponde perguntas   sobre saúde.O projeto está hospedado no Heroku e se conecta com o Zilliz Cloud, um banco de dados Milvus auto gerenciado.Utilizei como Sentence Transformer o modelo
  all-MiniLM-L6-v2, que reduziu bastante o tamanho do container,já que o limite do Heroku é 2GB.
</p>

<p align="center">
  <img src="RodMed.png" alt="Sistema Construído">
</p>


