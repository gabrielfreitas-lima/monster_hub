"""
bt_detector.py
Especialista em dispositivos Bluetooth no Windows.

NOTAS PARA O TIME DE DESENVOLVIMENTO:
1. Por que WinRT e não WMI? O WMI é instável e lento para Bluetooth no Windows. O WinRT 
   (usado via bibliotecas 'winrt' do Python) é a API oficial da Microsoft para rádio e Bluetooth.
2. Como lemos a bateria? Dispositivos BLE (Low Energy) usam GATT via 'bleak'. Dispositivos Clássicos 
   (como fones A2DP) não expõem a bateria facilmente, então usamos um script PowerShell 
   para ler a propriedade do Windows ({104EA319-...}).
3. Cache de categorias: Se o fone estiver desligado, o Windows não sabe se é fone ou mouse. 
   Salvamos a categoria em 'bt_categorias.json' para lembrar na próxima vez.
"""

import asyncio
import json
import os
import re
import subprocess
import sys
import io

from bleak import BleakClient
from winrt.windows.devices.bluetooth import (
    BluetoothConnectionStatus,
    BluetoothDevice,
    BluetoothLEDevice,
)
from winrt.windows.devices.enumeration import DeviceInformation
from winrt.windows.devices.radios import Radio, RadioKind, RadioState

from device_classifier import classificar

BATTERY_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
GENERICAS = {"bluetooth", "genérico", "generico", "desconhecido", "outro"}

# --------------------------------------------------------------------------
# Utilitários Básicos
# --------------------------------------------------------------------------
async def is_bluetooth_enabled() -> bool:
    """
    Verifica rapidamente se o rádio Bluetooth está ligado.
    Se estiver desligado, o app abre instantaneamente (pula o escaneamento).
    """
    try:
        radios = await Radio.get_radios_async()
        for radio in radios:
            if radio.kind == RadioKind.BLUETOOTH:
                return radio.state == RadioState.ON
    except Exception as e:
        print(f"Não foi possível verificar o rádio BT: {e}")
        return False
    return False

def extract_mac(device_id: str) -> str | None:
    """Extrai o MAC real de um InstanceId do Windows."""
    m = (
        re.search(r"DEV_([0-9A-Fa-f]{12})", device_id)
        or re.search(r"&([0-9A-Fa-f]{12})_C", device_id)
    )
    if not m:
        return None
    h = m.group(1).upper()
    return ":".join(h[i:i + 2] for i in range(0, 12, 2))

def _addr_to_mac(address: int) -> str:
    """Converte o endereço numérico do WinRT para o formato MAC padrão (AA:BB:CC:DD:EE:FF)."""
    h = f"{address:012X}"
    return ":".join(h[i:i + 2] for i in range(0, 12, 2))

def _appearance_raw(dev: BluetoothLEDevice) -> int | None:
    """Lê o 'Appearance' (tipo do dispositivo) do BLE sem crashar o app se falhar."""
    try:
        return dev.appearance.raw_value
    except Exception:
        return None

# --------------------------------------------------------------------------
# Memória de Categorias (Para quando o dispositivo estiver desligado)
# --------------------------------------------------------------------------
CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bt_categorias.json")

def _carregar_cache() -> dict:
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _salvar_cache(cache: dict) -> None:
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Não foi possível salvar o cache de categorias: {e}")

def _resolver_categorias(devices: dict) -> None:
    """
    Se a categoria veio vaga (ex: aparelho desligado), busca do cache usando o MAC.
    """
    cache = _carregar_cache()
    mudou = False
    for mac, d in devices.items():
        if d["category"] in GENERICAS:
            lembrada = cache.get(mac)
            if lembrada and lembrada not in GENERICAS:
                d["category"] = lembrada
        elif cache.get(mac) != d["category"]:
            # Atualiza o cache com a nova categoria descoberta
            cache[mac] = d["category"]
            mudou = True
    if mudou:
        _salvar_cache(cache)

# --------------------------------------------------------------------------
# Leitura de Bateria (BLE via Bleak e Clássico via PowerShell)
# --------------------------------------------------------------------------
async def read_battery_ble(address: str) -> int | None:
    """Lê a bateria de dispositivos BLE usando o protocolo GATT padrão."""
    try:
        async with BleakClient(address, timeout=3.0) as client:
            data = await client.read_gatt_char(BATTERY_UUID)
            return int(data[0])
    except Exception:
        return None

# Script PowerShell que varre o registro do Windows em busca da bateria de fones clássicos
_PS_BATTERY = r"""
$ErrorActionPreference = 'SilentlyContinue'
$key = '{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2'
$res = @{}
Get-PnpDevice -Class Bluetooth | ForEach-Object {
    $mac = $null
    if ($_.InstanceId -match 'DEV_([0-9A-Fa-f]{12})') { $mac = $matches[1].ToUpper() }
    elseif ($_.InstanceId -match '&([0-9A-Fa-f]{12})_C') { $mac = $matches[1].ToUpper() }
    if ($mac) {
        $p = Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName $key
        if ($p -and $p.Data -ne $null -and $p.Type -ne 'Empty') {
            $res[$mac] = [int]$p.Data
        }
    }
}
if ($res.Count -gt 0) { $res | ConvertTo-Json -Compress } else { '{}' }
"""

def _battery_classic_map_sync() -> dict[str, int]:
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", _PS_BATTERY],
            capture_output=True, text=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        out = result.stdout.strip()
        if not out: return {}
        
        raw = json.loads(out)
        mapa = {}
        for hex_mac, valor in raw.items():
            mac = ":".join(hex_mac[i:i + 2] for i in range(0, 12, 2))
            if 0 <= int(valor) <= 100:
                mapa[mac] = int(valor)
        return mapa
    except Exception as e:
        print(f"Erro ao ler bateria clássica via PowerShell: {e}")
        return {}

async def read_battery_classic_map() -> dict[str, int]:
    # Roda o PowerShell numa thread separada para não travar o servidor web
    return await asyncio.to_thread(_battery_classic_map_sync)

# --------------------------------------------------------------------------
# Enumeração de Dispositivos (WinRT)
# --------------------------------------------------------------------------
async def _enumerar_classicos(devices: dict) -> None:
    """Busca dispositivos Bluetooth Clássicos (Áudio, etc) pareados."""
    try:
        sel = BluetoothDevice.get_device_selector_from_pairing_state(True)
        infos = await DeviceInformation.find_all_async_aqs_filter(sel)
        for info in infos:
            try:
                dev = await BluetoothDevice.from_id_async(info.id)
                if not dev: continue
                
                mac = _addr_to_mac(dev.bluetooth_address)
                novo = {
                    "name": (dev.name or "").strip() or "Periférico Genérico",
                    "connected": dev.connection_status == BluetoothConnectionStatus.CONNECTED,
                    "category": classificar(nome=dev.name, cod=dev.class_of_device.raw_value, fallback="bluetooth"),
                    "is_ble": False,
                    "mac": mac,
                }
                
                # PROTEÇÃO: Se o BLE já adicionou, mescla em vez de sobrescrever
                if mac in devices:
                    devices[mac]["connected"] = devices[mac]["connected"] or novo["connected"]
                    if devices[mac]["category"] in GENERICAS:
                        devices[mac]["category"] = novo["category"]
                else:
                    devices[mac] = novo
                    
                dev.close()
            except Exception as e:
                print(f"Erro ao ler dispositivo clássico {info.id}: {e}")
    except Exception as e:
        print(f"[BT] Falha ao listar dispositivos clássicos: {e}")

async def _enumerar_ble(devices: dict) -> None:
    """Busca dispositivos Bluetooth Low Energy (BLE) pareados."""
    try:
        sel = BluetoothLEDevice.get_device_selector_from_pairing_state(True)
        infos = await DeviceInformation.find_all_async_aqs_filter(sel)
        for info in infos:
            try:
                dev = await BluetoothLEDevice.from_id_async(info.id)
                if not dev: continue
                
                mac = _addr_to_mac(dev.bluetooth_address)
                connected = dev.connection_status == BluetoothConnectionStatus.CONNECTED

                if mac in devices:
                    # Se o mesmo aparelho aparecer no clássico e no BLE, mescla as informações
                    devices[mac]["connected"] = devices[mac]["connected"] or connected
                    devices[mac]["is_ble"] = True
                else:
                    devices[mac] = {
                        "name": (dev.name or "").strip() or "Periférico Genérico",
                        "connected": connected,
                        "category": classificar(nome=dev.name, appearance=_appearance_raw(dev), fallback="bluetooth"),
                        "is_ble": True,
                        "mac": mac,
                    }
                dev.close()
            except Exception as e:
                print(f"Erro ao ler dispositivo BLE {info.id}: {e}")
    except Exception as e:
        print(f"[BT] Falha ao listar dispositivos BLE: {e}")

# --------------------------------------------------------------------------
# Função Principal
# --------------------------------------------------------------------------
async def get_bt_devices() -> list[dict]:
    """Função que o api.py chama para pegar todos os dispositivos Bluetooth."""
    
    # 1. Checagem rápida: Se o Bluetooth estiver desligado, economiza 5 segundos de espera!
    if not await is_bluetooth_enabled():
        return []

    devices: dict[str, dict] = {}

    # 2. Enumera Clássico e BLE em PARALELO (Muito mais rápido)
    await asyncio.gather(
        _enumerar_classicos(devices),
        _enumerar_ble(devices)
    )
    
    # 3. Resolve categorias (usa o cache se necessário)
    _resolver_categorias(devices)

    # 4. Limpa nomes genéricos que o Windows às vezes coloca
    devices = {
        mac: d for mac, d in devices.items()
        if d["name"] not in ("Periférico Genérico", "Desconhecido")
    }

    conectados = {mac: d for mac, d in devices.items() if d["connected"]}

    # 5. Busca a bateria (Apenas para os conectados)
    battery_map = await read_battery_classic_map() if conectados else {}
    for mac, d in conectados.items():
        d["battery"] = battery_map.get(mac)

    # 6. Se algum dispositivo BLE conectado ainda não tiver bateria, tenta via GATT
    async def _ble_battery(d: dict):
        if d.get("battery") is None and d["is_ble"]:
            d["battery"] = await read_battery_ble(d["mac"])

    await asyncio.gather(*(_ble_battery(d) for d in conectados.values()))

    # 7. Monta o dicionário final no formato padrão que o Frontend e o api.py esperam
    resultado = []
    for d in devices.values():
        resultado.append({
            "name": d["name"],
            "type": "Bluetooth",
            "connection": "📶 Bluetooth",
            "battery": d.get("battery") if d["connected"] else None,
            "vendor_id": None, # Bluetooth não usa VID/PID
            "product_id": None,
            "icon": "", # O Frontend resolve isso no JS
            "connected": d["connected"],
            "category": d["category"],
        })

    # Ordena para colocar os conectados primeiro
    resultado.sort(key=lambda x: (not x["connected"], x["name"].lower()))
    return resultado


if __name__ == "__main__":
    # Bloco de teste: Executar 'python bt_detector.py' diretamente no terminal
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        
    print("Testando bt_detector.py...")
    for item in asyncio.run(get_bt_devices()):
        estado = "CONECTADO" if item["connected"] else "desconectado"
        bat = f'{item["battery"]}%' if item["battery"] is not None else "N/A"
        print(f'{item["name"]:<28} {item["category"]:<14} {estado:<13} bateria: {bat}')