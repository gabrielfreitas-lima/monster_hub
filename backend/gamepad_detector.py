import io
import json
import os
import re
import sys
import wmi
import pythoncom

DB_PATH = os.path.join(os.path.dirname(__file__), "known_gamepads.json")
try:
    with open(DB_PATH, "r", encoding="utf-8") as f:
        KNOWN_GAMEPADS = json.load(f)
except Exception:
    KNOWN_GAMEPADS = {}

MARCAS = {
    "3537": "GameSir", "045E": "Microsoft", "054C": "Sony", "057E": "Nintendo",
    "2DC8": "8BitDo", "0F0D": "HORI", "0E6F": "PDP",
}

RE_VIDPID = re.compile(r"VID_([0-9A-F]{4})&PID_([0-9A-F]{4})", re.I)
RE_IG = re.compile(r"&IG_\d+", re.I)
RE_NOME_CONTROLE = re.compile(
    r"controlador de jogo|game controller|gamepad|joystick|xbox 360|xbox one|xinput", re.I
)
USO_HID_GAMEPAD = ("UP:0001_U:0005", "UP:0001_U:0004")

def _e_controle(e: dict) -> bool:
    if (e.get("pnp_class") or "") == "XnaComposite": return True
    if RE_IG.search(e.get("device_id") or ""): return True
    ids = " ".join(e.get("hardware_ids") or []).upper()
    if any(u in ids for u in USO_HID_GAMEPAD): return True
    return bool(RE_NOME_CONTROLE.search(e.get("name") or ""))

def _ler_entradas_wmi() -> list[dict]:
    pythoncom.CoInitialize()
    try:
        c = wmi.WMI()
        saida = []
        for dev in c.Win32_PnPEntity():
            if getattr(dev, "Present", True) is False: continue
            ids = list(dev.HardwareID or []) + list(getattr(dev, "CompatibleID", None) or [])
            saida.append({
                "device_id": dev.DeviceID or "",
                "pnp_class": dev.PNPClass,
                "name": dev.Name or "",
                "hardware_ids": ids,
            })
        return saida
    finally:
        pythoncom.CoUninitialize()

def get_gamepads() -> list[dict]:
    pythoncom.CoInitialize()
    try:
        entradas = _ler_entradas_wmi()
        agrupados = {}

        for e in entradas:
            did = e.get("device_id") or ""
            up = did.upper()
            
            if not (up.startswith("USB\\") or up.startswith("HID\\")):
                continue
            if not _e_controle(e):
                continue
                
            m = RE_VIDPID.search(did)
            if not m: continue
            vid, pid = m.group(1).upper(), m.group(2).upper()
            chave = f"{vid}_{pid}"

            if chave in KNOWN_GAMEPADS:
                db_info = KNOWN_GAMEPADS[chave]
                nome = db_info.get("name", "Controle Genérico")
                tipo = db_info.get("category", "controle")
                conexao = db_info.get("connection")
                if not conexao:
                    conexao = "📡 Wireless 2.4GHz" if "wireless" in nome.lower() or "dongle" in nome.lower() else "🔌 USB (Cabo)"
            else:
                marca = MARCAS.get(vid, "")
                nome = f"Controle {marca}" if marca else f"Controle Genérico ({vid})"
                tipo = "Gamepad"
                conexao = "🎮 USB (Modo não mapeado)"

            # Limpa nomes estranhos
            nome = re.sub(r'\(.*?\)', '', nome).strip()
            nome = nome.replace(" .", "").strip()

            # A MÁGICA: Usa o VID_PID como master_id. 
            # Todas as interfaces do MESMO controle vão cair nessa mesma chave.
            master_id = f"GAMEPAD_{vid}_{pid}"

            if master_id not in agrupados:
                agrupados[master_id] = {
                    "name": nome,
                    "master_id": master_id,
                    "type": tipo,
                    "connection": conexao,
                    "battery": None,
                    "vendor_id": vid,
                    "product_id": pid,
                    "icon": "",
                    "connected": True,
                    "category": "controle",
                }

        return list(agrupados.values())
    except Exception as e:
        print(f"[Gamepad] Erro ao ler controles: {e}")
        return []
    finally:
        pythoncom.CoUninitialize()