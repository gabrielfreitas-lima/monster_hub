import json
import os
from datetime import datetime, timezone, timedelta

HISTORY_PATH = os.path.join(os.path.dirname(__file__), "historico_perifericos.json")

def carregar_historico() -> dict:
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def salvar_historico(hist: dict):
    try:
        with open(HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(hist, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Erro ao salvar histórico: {e}")

def aplicar_historico(lista_atual: list[dict]) -> list[dict]:
    """
    Cruza os dispositivos atuais com o histórico.
    Adiciona data da última conexão, selo 'NOVO' e aparelhos que sumiram.
    """
    hist = carregar_historico()
    agora = datetime.now(timezone.utc)
    resultado = []
    
    vistos_agora = set()

    for dev in lista_atual:
        # CORREÇÃO: Usa o master_id (único) em vez do nome (que pode colidir)
        chave = dev.get("master_id") or dev["name"]
        vistos_agora.add(chave)

        is_novo = False
        if chave not in hist:
            is_novo = True
            hist[chave] = {
                "ultima_conexao": agora.isoformat(),
                "novo": True,
                "visto_em": agora.isoformat(),
                "nome": dev["name"] # Guarda o nome bonito
            }
        else:
            if dev["connected"]:
                hist[chave]["ultima_conexao"] = agora.isoformat()
            
            data_visto = datetime.fromisoformat(hist[chave]["visto_em"])
            if (agora - data_visto) > timedelta(minutes=2):
                hist[chave]["novo"] = False
                
            is_novo = hist[chave].get("novo", False)

        dev["ultima_conexao"] = hist[chave]["ultima_conexao"]
        dev["novo"] = is_novo
        dev["memoria"] = False
        resultado.append(dev)

    # Adiciona aparelhos que estão no histórico mas não foram vistos agora
    for chave, dados in hist.items():
        if chave not in vistos_agora:
            data_ultima = datetime.fromisoformat(dados["ultima_conexao"])
            if (agora - data_ultima) > timedelta(days=90):
                continue
                
            resultado.append({
                "name": dados.get("nome", chave), # Usa o nome salvo, ou a chave como fallback
                "type": "Desconhecido",
                "connection": "Desconectado",
                "battery": None,
                "vendor_id": None,
                "product_id": None,
                "icon": "",
                "connected": False,
                "category": "outro",
                "ultima_conexao": dados["ultima_conexao"],
                "novo": False,
                "memoria": True
            })

    salvar_historico(hist)
    return resultado