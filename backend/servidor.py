"""
servidor.py
Ponto de entrada do Backend (Python).

NOTA PARA O TIME DE DESENVOLVIMENTO:
1. Por que `from api import app` e não `uvicorn.run("api:app")`?
   O PyInstaller precisa "enxergar" a importação estática para incluir o arquivo api.py 
   dentro do executável. Se usarmos string, o PyInstaller não encontra o arquivo e o .exe quebra.
   
2. Por que `log_config=None`?
   Como o app final é compilado com `--windowed` (sem janela preta de console), o Uvicorn 
   tenta configurar cores no terminal e crasha se não encontrar o `stdout`. Desativar isso 
   impede que o servidor feche sozinho ao abrir o app.
"""

import uvicorn
import multiprocessing
import logging
from api import app 

if __name__ == '__main__':
    # Obrigatório para PyInstaller no Windows evitar loops infinitos de inicialização
    multiprocessing.freeze_support()
    
    # Configura o log para aparecer de forma legível no arquivo backend_log.txt (capturado pelo Electron)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Inicia o servidor FastAPI
    uvicorn.run(
        app, 
        host="127.0.0.1", 
        port=8000, 
        log_config=None # Impede o Uvicorn de tentar ler as cores do terminal
    )