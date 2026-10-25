import asyncio
import traceback
import os
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from historico import aplicar_historico
from usb_detector import get_usb_devices, get_base_name, KNOWN_DEVICES
from bt_detector import get_bt_devices
from hid_battery import get_wireless_devices
from gamepad_detector import get_gamepads, KNOWN_GAMEPADS

app = FastAPI(title="MONSTER HUB API", version="0.1.4")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

class Peripheral(BaseModel):
    name: str
    type: str
    connection: str
    battery: int | None = None
    vendor_id: str | None = None
    product_id: str | None = None
    icon: str 
    connected: bool
    category: str | None = None
    ultima_conexao: str | None = None
    novo: bool = False
    memoria: bool = False

OCULTAR_BATERIA_NO_CABO = True            
FONTES_DERIVADAS = {"AudioEndpoint", "MEDIA"}   

def _sem_emoji(txt: str) -> str:
    return txt.replace("🔌 ", "").replace("📶 ", "").replace("📡 ", "")

def _e_cabo(d: dict) -> bool:
    return d.get("mode") == "cabo" or "Cabo" in (d.get("connection") or "")

def merge_devices(lista_completa, bt_devices=None):
    # 1. Cria o dicionário do catálogo (Nome -> master_id)
    nome_para_master = {}
    for k, info in KNOWN_DEVICES.items():
        if "name" in info and "master_id" in info:
            nome_para_master[info["name"].lower().strip()] = info["master_id"]

    grupos = {}
    for dev in lista_completa:
        nome_dev = (dev.get("name") or "").lower().strip()
        chave = nome_para_master.get(nome_dev)
        
        if not chave:
            chave = dev.get("master_id")
            
        if not chave:
            chave = get_base_name(dev["name"])
            
        grupos.setdefault(chave, []).append(dev)

    mesclados = []
    for devs in grupos.values():
        cabos = [d for d in devs if _e_cabo(d)]

        if cabos:
            item = cabos[0].copy()
            item["connection"] = "🔌 USB (Cabo)"
            item["connected"] = any(d.get("connected") for d in cabos)
            item["mode"] = "cabo"

            fonte = next((d for d in cabos + devs if d.get("type") not in (None, "Wireless")), None)
            if fonte:
                item["type"] = fonte["type"]
                item["icon"] = fonte["icon"]

            item["battery"] = None if OCULTAR_BATERIA_NO_CABO else next(
                (d["battery"] for d in devs if d.get("battery") is not None), None
            )
        else:
            item = devs[0].copy()
            item["connected"] = False
            driver_timeout = False

            for dev in devs:
                if dev.get("battery") is not None:
                    item["battery"] = dev["battery"]
                
                if dev.get("battery_driver") and not dev.get("connected"):
                    driver_timeout = True
                elif dev.get("connected"):
                    item["connected"] = True

                if dev.get("type") in FONTES_DERIVADAS | {"Wireless"}:
                    item["type"] = dev["type"]
                    item["icon"] = dev["icon"]
                    
                if dev["connection"] not in item["connection"]:
                    item["connection"] += f" + {_sem_emoji(dev['connection'])}"

            if driver_timeout:
                item["connected"] = False

        item["_real"] = any(
            d.get("connected")
            and d.get("type") not in FONTES_DERIVADAS | {"Bluetooth"}
            and "Bluetooth" not in (d.get("connection") or "")
            for d in devs
        )
        
        # 👇 A NOVA FLAG: Salva se o driver de bateria falhou (offline)
        item["_offline_driver"] = any(d.get("battery_driver") and not d.get("connected") for d in devs)
        
        mesclados.append(item)

    if bt_devices:
        bt_por_id = {d.get("master_id"): d for d in bt_devices if d.get("master_id")}
        bt_por_nome = {get_base_name(d["name"]): d for d in bt_devices}

        for item in mesclados:
            if item.get("mode") == "cabo":
                continue
            
            # 👇 SE O DRIVER FALHOU, IGNORA O BLUETOOTH E FORÇA DESCONECTADO
            if item.get("_offline_driver"):
                item["connected"] = False
                item["battery"] = None
                continue # Pula a mesclagem com BT
            
            bt = bt_por_id.get(item.get("master_id")) or bt_por_nome.get(get_base_name(item["name"]))
            if not bt:
                continue
                
            item["category"] = bt.get("category")
            item["connected"] = bt["connected"] or item["_real"]
            if not item["connected"]:
                item["battery"] = None
            elif bt.get("battery") is not None:
                item["battery"] = bt["battery"]

    for item in mesclados:
        item.pop("_real", None)
        item.pop("_offline_driver", None) # Limpa a flag temporária

    lixo = {
        "AURA LED Controller", "Periférico Genérico", "Desconhecido",
        "Teclado (Genérico)", "Mouse (Genérico)"
    }
    
    # Filtra o lixo E os dispositivos que tiveram timeout no driver de bateria
    return [i for i in mesclados if i["name"] not in lixo and not (i.get("battery_driver") and i.get("connected") is False)]

@app.get("/peripherals", response_model=list[Peripheral])
async def peripherals():
    fontes = {
        "usb": asyncio.to_thread(get_usb_devices),
        "wireless": asyncio.to_thread(get_wireless_devices),
        "bt": get_bt_devices(),
        "gamepads": asyncio.to_thread(get_gamepads),
    }
    resultados = await asyncio.gather(*fontes.values(), return_exceptions=True)

    listas = {}
    for nome, r in zip(fontes.keys(), resultados):
        if isinstance(r, Exception):
            traceback.print_exception(type(r), r, r.__traceback__)
            print(f"Erro na fonte '{nome}': {r}")
            listas[nome] = []
        else:
            listas[nome] = r
            
    listas["usb"] = [d for d in listas["usb"] if d.get("vendor_id") or d.get("master_id")]
    
    todos = listas["usb"] + listas["wireless"] + listas["bt"] + listas["gamepads"]
    todos_mesclados = merge_devices(todos, listas["bt"])

    def ordem_conexao(item):
        if "USB" in item["connection"]: return 1
        if "Wireless" in item["connection"]: return 2
        if "Bluetooth" in item["connection"]: return 3
        return 4

    todos_mesclados.sort(key=ordem_conexao)
    
    # 1. Aplica o histórico
    com_historico = aplicar_historico(todos_mesclados)
    
    # 2. 👇 A CORREÇÃO GERAL ANTI-FANTASMA (V3) 👇
    # Junta todos os bancos de dados em um só para facilitar a busca
    todos_os_dbs = {**KNOWN_DEVICES, **KNOWN_GAMEPADS}
    
    for item in com_historico:
        vid = item.get("vendor_id")
        pid = item.get("product_id")
        
        db_info = None
        
        # Tentativa 1: Buscar por VID e PID (se existirem)
        if vid and pid:
            db_info = todos_os_dbs.get(f"{vid}_{pid}")
            
        # Tentativa 2: Se não achou (ou se VID/PID são null), buscar pelo NOME
        if not db_info:
            nome_item = item.get("name", "").lower().strip()
            for k, v in todos_os_dbs.items():
                if v.get("name", "").lower().strip() == nome_item:
                    db_info = v
                    break
        
        # Se encontramos o dispositivo no JSON, aplicamos a verdade
        if db_info:
            item["name"] = db_info.get("name", item["name"])
            item["category"] = db_info.get("category", item.get("category", "outro"))
            
            # Só corrigimos a conexão se ele estiver offline
            if not item.get("connected"):
                modo = db_info.get("mode")
                conexao_json = db_info.get("connection")
                
                if modo == "dongle":
                    item["connection"] = "📡 Wireless 2.4GHz"
                    item["type"] = "Wireless"
                elif modo == "cabo":
                    item["connection"] = "🔌 USB (Cabo)"
                    item["type"] = db_info.get("category", "Controle").capitalize()
                elif conexao_json:
                    item["connection"] = conexao_json
                    
    # 👆 FIM DA CORREÇÃO GERAL V3 👆

    return com_historico

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/debug")
async def debug():
    usb_task = asyncio.to_thread(get_usb_devices)
    wireless_task = asyncio.to_thread(get_wireless_devices)
    bt_task = get_bt_devices()
    gamepad_task = asyncio.to_thread(get_gamepads)
    
    usb, wireless, bt, gamepads = await asyncio.gather(usb_task, wireless_task, bt_task, gamepad_task)

    return {
        "usb": usb,
        "wireless": wireless,
        "bt": bt,
        "gamepads": gamepads
    }