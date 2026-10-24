"""
bt_detector.py
Especialista em dispositivos Bluetooth no Windows.
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
    try:
        radios = await Radio.get_radios_async()
        for radio in radios:
            if radio.kind == RadioKind.BLUETOOTH:
                return radio.state == RadioState.ON
    except Exception as e:
        print(f"Não foi possível verificar o rádio BT: {e}")
        return False
    return False

def _addr_to_mac(address: int) -> str:
    h = f"{address:012X}"
    return ":".join(h[i:i + 2] for i in range(0, 12, 2))

def _appearance_raw(dev: BluetoothLEDevice) -> int | None:
    try:
        return dev.appearance.raw_value
    except Exception:
        return None

# --------------------------------------------------------------------------
# Memória de Categorias
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
    cache = _carregar_cache()
    mudou = False
    for mac, d in devices.items():
        if d["category"] in GENERICAS:
            lembrada = cache.get(mac)
            if lembrada and lembrada not in GENERICAS:
                d["category"] = lembrada
        elif cache.get(mac) != d["category"]:
            cache[mac] = d["category"]
            mudou = True
    if mudou:
        _salvar_cache(cache)

# --------------------------------------------------------------------------
# Leitura de Bateria (A Grande Melhoria baseada no estudo_bateria.py)
# --------------------------------------------------------------------------
async def read_battery_ble(address: str) -> int | None:
    try:
        async with BleakClient(address, timeout=3.0) as client:
            data = await client.read_gatt_char(BATTERY_UUID)
            return int(data[0])
    except Exception:
        return None

# O script PowerShell agora busca o MAC em QUALQUER nó PnP, não só na classe Bluetooth.
_PS_BATTERY = r"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$chave = '{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2'
$macs = @(__MACS__)

# Lista todos os dispositivos presentes no PC inteiro
$todos = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue

$saida = @()
foreach ($mac in $macs) {
    # Busca em qualquer nó que contenha o MAC
    foreach ($no in ($todos | Where-Object { $_.InstanceId -like "*$mac*" })) {
        $p = Get-PnpDeviceProperty -InstanceId $no.InstanceId -KeyName $chave -ErrorAction SilentlyContinue
        if ($p -and $null -ne $p.Data) {
            try {
                $valor = [int]$p.Data
                if ($valor -ge 0 -and $valor -le 100) {
                    $saida += [PSCustomObject]@{ Mac = $mac; Bateria = $valor }
                    break
                }
            } catch { }
        }
    }
}
if ($saida.Count -gt 0) { ConvertTo-Json -InputObject @($saida) }
"""

def _battery_classic_map_sync(macs_limpos: list[str]) -> dict[str, int]:
    if not macs_limpos:
        return {}
        
    lista_ps = ",".join(f"'{m}'" for m in macs_limpos)
    script = _PS_BATTERY.replace("__MACS__", lista_ps)
    
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        out = result.stdout.strip()
        if not out: return {}
        
        raw = json.loads(out)
        if isinstance(raw, dict): raw = [raw]
        
        mapa = {}
        for item in raw:
            mac_limpo = item["Mac"]
            # Recoloca os dois pontos para o formato padrão do Python
            mac_formatado = ":".join(mac_limpo[i:i + 2] for i in range(0, 12, 2))
            mapa[mac_formatado] = int(item["Bateria"])
        return mapa
    except Exception as e:
        print(f"Erro ao ler bateria clássica via PowerShell: {e}")
        return {}

async def read_battery_classic_map(macs: list[str]) -> dict[str, int]:
    # Remove os dois pontos para a busca no Windows
    macs_limpos = [m.replace(":", "") for m in macs]
    return await asyncio.to_thread(_battery_classic_map_sync, macs_limpos)

# --------------------------------------------------------------------------
# Enumeração de Dispositivos
# --------------------------------------------------------------------------
async def _enumerar_classicos(devices: dict) -> None:
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
    if not await is_bluetooth_enabled():
        return []

    devices: dict[str, dict] = {}

    await asyncio.gather(
        _enumerar_classicos(devices),
        _enumerar_ble(devices)
    )
    
    _resolver_categorias(devices)

    devices = {
        mac: d for mac, d in devices.items()
        if d["name"] not in ("Periférico Genérico", "Desconhecido")
    }

    conectados = {mac: d for mac, d in devices.items() if d["connected"]}

    # 5. Busca a bateria passando os MACs conectados (Novo método)
    macs_conectados = list(conectados.keys())
    battery_map = await read_battery_classic_map(macs_conectados)
    
    for mac, d in conectados.items():
        d["battery"] = battery_map.get(mac)

    # 6. Plano B: Se o Windows não deu a bateria, tenta via BLE (GATT)
    async def _ble_battery(d: dict):
        if d.get("battery") is None and d["is_ble"]:
            d["battery"] = await read_battery_ble(d["mac"])

    await asyncio.gather(*(_ble_battery(d) for d in conectados.values()))

    resultado = []
    for d in devices.values():
        resultado.append({
            "name": d["name"],
            "type": "Bluetooth",
            "connection": "📶 Bluetooth",
            "battery": d.get("battery") if d["connected"] else None,
            "vendor_id": None,
            "product_id": None,
            "icon": "",
            "connected": d["connected"],
            "category": d["category"],
        })

    resultado.sort(key=lambda x: (not x["connected"], x["name"].lower()))
    return resultado

if __name__ == "__main__":
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        
    print("Testando bt_detector.py...")
    for item in asyncio.run(get_bt_devices()):
        estado = "CONECTADO" if item["connected"] else "desconectado"
        bat = f'{item["battery"]}%' if item["battery"] is not None else "N/A"
        print(f'{item["name"]:<28} {item["category"]:<14} {estado:<13} bateria: {bat}')