import wmi
import pythoncom
import re
import os
import json
import logging
import hid

from device_classifier import classificar, rotulo

logging.basicConfig(
    filename='usb_detector_debug.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

DB_PATH = os.path.join(os.path.dirname(__file__), "known_devices.json")
try:
    with open(DB_PATH, "r", encoding="utf-8") as f:
        KNOWN_DEVICES = json.load(f)
except Exception:
    KNOWN_DEVICES = {}

INTERESTING_CLASSES = {"HIDClass", "USB", "AudioEndpoint", "MEDIA", "Mouse", "Keyboard"}

def extract_ids(dev) -> tuple[str | None, str | None]:
    ids_to_check = [dev.DeviceID] if dev.DeviceID else []
    if dev.HardwareID:
        ids_to_check.extend(dev.HardwareID)
    vid = pid = None
    for id_str in ids_to_check:
        if not id_str: continue
        for part in id_str.split("\\"):
            if "VID_" in part: vid = part.split("VID_")[1][:4].upper()
            if "PID_" in part: pid = part.split("PID_")[1][:4].upper()
        if vid and pid: return vid, pid
    return vid, pid

def get_base_name(name: str) -> str:
    if not name: return "Desconhecido"
    name = re.sub(r'\(.*?\)', '', name)
    ruidos = [
        "A2DP SNK", "A2DP", "Hands-Free", "Handsfree", "Stereo", "Mic", 
        "Microfone", "Headphone", "Headset", "Alto-falantes", "Telefone",
        "Audio", "HID-compliant", "HID", "compatível com HID", "Controlador de jogo",
        "Dispositivo de Entrada", "Consumer Control", "System Control", 
        "conforme", "Device", "Dispositivo", "USB", "Bluetooth", "Wireless",
        "HF", "AG", "Avrcp"
    ]
    for ruido in ruidos:
        name = re.sub(r'\b' + re.escape(ruido) + r'\b', '', name, flags=re.IGNORECASE)
    return name.strip(" -_")

def get_usb_devices() -> list[dict]:
    print(f"[USB_DETECTOR] Iniciando leitura. PID={os.getpid()}", flush=True)
    pythoncom.CoInitialize()
    try:
        c = wmi.WMI()
        agrupados = {}

        ignorar_nomes = [
            "Composite", "Host Controller", "Root Hub", "Generic USB Hub", 
            "Dispositivo definido pelo fornecedor", "Virtual", "AMD High Definition",
            "Consumer Control", "System Control", "Service", "Serviço",
            "Streaming", "Realtek", "Alexa", "Echo", "Leitor de notificação", 
            "Código de barras", "Bar Code", "TeamViewer", "I2C HID", "Synaptics", "Parsec",
            "Controle", "Gamepad", "Xbox", "Xinput", "GameSir", "Joystick",
            "compativel com", "compatível com", "conforme", "Controlador XBOX"
        ]

        # ===== PARTE 1: WMI (Tenta pegar tudo que é possível) =====
        for dev in c.Win32_PnPEntity():
            if getattr(dev, "Present", True) is False or getattr(dev, "ConfigManagerErrorCode", 0) in {24, 45}:
                continue

            if not dev.Name or dev.PNPClass not in INTERESTING_CLASSES:
                continue
            
            if any(palavra.lower() in dev.Name.lower() for palavra in ignorar_nomes):
                continue 
                
            dev_id = dev.DeviceID or ""
            
            if "BTHENUM" in dev_id or "BTHLE" in dev_id:
                continue
                
            if "USB" not in dev_id.upper() and "HID" not in dev_id.upper():
                continue

            vid, pid = extract_ids(dev)
            
            # --- FILTRO ANTI-GAMEPAD ---
            # Se o VID for de um controle conhecido (GameSir, Xbox, Sony, etc),
            # ignora no USB (o gamepad_detector.py vai cuidar dele).
            VIDS_GAMEPADS = {"3537", "045E", "054C", "057E", "2DC8"}
            if vid and vid.upper() in VIDS_GAMEPADS:
                continue
            # ---------------------------
            
            if not vid or not pid:
                continue
            nome_base = None
            categoria = "periferico"
            master_id = None
            mode = "desconhecido"
            
            if vid and pid:
                chave_busca = f"{vid}_{pid}"
                if chave_busca in KNOWN_DEVICES:
                    db_info = KNOWN_DEVICES[chave_busca]
                    nome_base = db_info["name"]
                    categoria = db_info.get("category", "periferico")
                    master_id = db_info.get("master_id", nome_base)
                    mode = db_info.get("mode", "desconhecido")
            
            if not nome_base:
                nome_bruto = dev.Name
                nome_limpo = get_base_name(nome_bruto)
                
                if dev.PNPClass in ["Mouse", "Keyboard"]:
                    nome_base = "Mouse (Genérico)" if dev.PNPClass == "Mouse" else "Teclado (Genérico)"
                    categoria = "mouse" if dev.PNPClass == "Mouse" else "teclado"
                elif dev.HardwareID:
                    hw_ids = " ".join(dev.HardwareID).upper()
                    if "HID_DEVICE_SYSTEM_MOUSE" in hw_ids:
                        nome_base = "Mouse (Genérico)"
                        categoria = "mouse"
                    elif "HID_DEVICE_SYSTEM_KEYBOARD" in hw_ids:
                        nome_base = "Teclado (Genérico)"
                        categoria = "teclado"
                    else:
                        nome_base = nome_limpo if nome_limpo and len(nome_limpo) > 2 else nome_bruto
                        categoria = classificar(nome=nome_bruto, pnp_class=dev.PNPClass)
                else:
                    nome_base = nome_limpo if nome_limpo and len(nome_limpo) > 2 else nome_bruto
                    categoria = classificar(nome=nome_bruto, pnp_class=dev.PNPClass)
                
                if nome_base in ["Dispositivo de Entrada USB", "USB Input Device", "HID-compliant device", "Dispositivo definido pelo fornecedor"]:
                    continue

                master_id = f"{vid}_{pid}" if vid and pid else nome_base
                
                if any(w in nome_bruto.lower() for w in ["dongle", "receiver", "wireless"]):
                    mode = "dongle"
                else:
                    mode = "cabo"

            if mode == "dongle":
                conexao = "📡 Wireless 2.4GHz"
                tipo_hardware = "Wireless"
            else:
                conexao = "🔌 USB (Cabo)"
                tipo_hardware = rotulo(categoria).capitalize()

            if master_id not in agrupados:
                agrupados[master_id] = {
                    "name": nome_base,
                    "master_id": master_id,
                    "mode": mode,
                    "type": tipo_hardware,
                    "connection": conexao,
                    "battery": None, 
                    "vendor_id": vid,
                    "product_id": pid,
                    "icon": "", 
                    "connected": True,
                    "category": categoria
                }

        # ===== PARTE 2: FALLBACK HID =====
        # Roda APÓS o WMI terminar de listar tudo. Se o WMI falhou em achar algum,
        # o hid vai lá no barramento e adiciona.
        try:
            for d in hid.enumerate():
                vid = f"{d['vendor_id']:04X}"
                pid = f"{d['product_id']:04X}"
                device_key = f"{vid}_{pid}"
                
                if device_key in KNOWN_DEVICES:
                    db_info = KNOWN_DEVICES[device_key]
                    master_id = db_info.get("master_id", device_key)
                    
                    # Se o WMI já encontrou, não faz nada
                    if master_id not in agrupados:
                        mode = db_info.get("mode", "dongle")
                        conexao = "📡 Wireless 2.4GHz" if mode == "dongle" else "🔌 USB (Cabo)"
                        tipo = "Wireless" if mode == "dongle" else db_info.get("category", "periferico").capitalize()
                        
                        agrupados[master_id] = {
                            "name": db_info["name"],
                            "master_id": master_id,
                            "mode": mode,
                            "type": tipo,
                            "connection": conexao,
                            "battery": None, 
                            "vendor_id": vid,
                            "product_id": pid,
                            "icon": "", 
                            "connected": True,
                            "category": db_info.get("category", "periferico")
                        }
        except Exception as e:
            print(f"[USB_DETECTOR] Erro no fallback HID: {e}")

        print(f"[USB_DETECTOR] Finalizado. Dispositivos encontrados: {len(agrupados)}.", flush=True)
        return list(agrupados.values())
    finally:
        pythoncom.CoUninitialize()