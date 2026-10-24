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
from gamepad_detector import get_gamepads

app = FastAPI(title="MONSTER HUB API", version="0.1.1")

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
        # CORREÇÃO DO CLAUDE: Invertemos a ordem de prioridade!
        
        # 1. Prioridade: O catálogo conhece esse nome?
        nome_dev = (dev.get("name") or "").lower().strip()
        chave = nome_para_master.get(nome_dev)
        
        # 2. Senão, usa o master_id que o detector gerou (vid_pid, BT_mac, etc.)
        if not chave:
            chave = dev.get("master_id")
            
        # 3. Último recurso: nome limpo
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
        mesclados.append(item)

    if bt_devices:
        # OTIMIZAÇÃO: Constrói os dicionários UMA VEZ SÓ antes do loop
        bt_por_id = {d.get("master_id"): d for d in bt_devices if d.get("master_id")}
        bt_por_nome = {get_base_name(d["name"]): d for d in bt_devices}

        for item in mesclados:
            if item.get("mode") == "cabo":
                continue
            
            # Usa o ID (se existir) ou cai pro Nome
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

    lixo = {"AURA LED Controller", "Periférico Genérico", "Desconhecido"}
    return [i for i in mesclados if i["name"] not in lixo]

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
    return aplicar_historico(todos_mesclados)

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