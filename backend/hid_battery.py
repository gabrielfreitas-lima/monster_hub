"""
hid_battery.py
Dongles/receptores 2.4GHz: detecção + leitura de bateria por "drivers" (um por fabricante).

Para adicionar um aparelho novo, o resto do app (api.py, frontend) não muda:
  1) known_devices.json:  "VID_PID": { ..., "battery_driver": "nome" }
  2) aqui:                @register("nome")  def read_nome(dev) -> BatteryReading

Campos opcionais no known_devices.json:
  "mode": "dongle" | "cabo"        (padrão: "dongle")
  "offline_on_timeout": true       (só ligue depois de confirmar, com captura, que o
                                    dongle fica mudo quando o aparelho está desligado)

Diagnóstico das interfaces HID (para achar a interface "vendor" usada pelo app oficial):
  python hid_battery.py --interfaces
"""

import json
import os
import sys
import threading
import time
from dataclasses import dataclass

import hid

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "known_devices.json")


def _carregar_db() -> dict:
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[HID] Não foi possível ler known_devices.json: {e}")
        return {}


KNOWN_DEVICES = _carregar_db()

USAGE_PAGE_VENDOR = 0xFF00   # interfaces "vendor-defined" começam aqui
MAX_INTERFACES = 4           # quantas interfaces tentar por aparelho
CACHE_TTL_S = 90             # por quanto tempo reaproveitar a última bateria lida
FALHAS_PARA_OFFLINE = 1      # timeouts seguidos antes de marcar desconectado


# --------------------------------------------------------------------------
# Contrato dos drivers
# --------------------------------------------------------------------------
@dataclass
class BatteryReading:
    percent: int | None = None      # 0–100; None = não conseguiu interpretar
    charging: bool | None = None    # None = o protocolo não informa / não decodificado
    responding: bool = True         # False = o dongle não respondeu (timeout/erro)


DRIVERS: dict = {}                  # nome -> função(dev) -> BatteryReading


def register(nome: str):
    def deco(fn):
        DRIVERS[nome] = fn
        return fn
    return deco


# --------------------------------------------------------------------------
# Drivers (só I/O; lock e abertura/fechamento do HID ficam por conta de quem chama)
# --------------------------------------------------------------------------
MCHOSE_CMD = bytes([0x55, 0x65, 0x01, 0x00])   # comando capturado (URB_INTERRUPT out)


def parse_mchose(resp: bytes) -> int | None:
    """Resposta capturada (URB_INTERRUPT in): 55 65 5A 02 00 ... (0x5A = 90%).

    Só existe UMA assinatura. O hidapi entrega o relatório sem byte extra: se o descritor
    não usa Report ID, o primeiro byte já é o 0x55 (no Windows o hidapi remove até o 0x00
    artificial que o sistema adiciona); se usa, o Report ID é o próprio 0x55.
    """
    if len(resp) >= 3 and resp[0] == 0x55 and resp[1] == 0x65 and 0 <= resp[2] <= 100:
        return resp[2]
    return None


def _drenar(dev) -> None:
    """Descarta relatórios antigos da fila de entrada (resposta atrasada de uma leitura anterior)."""
    try:
        dev.set_nonblocking(1)
        for _ in range(16):
            if not dev.read(64):
                break
    finally:
        try:
            dev.set_nonblocking(0)
        except Exception:
            pass


@register("mchose")
def read_mchose(dev) -> BatteryReading:
    try:
        _drenar(dev)

        # 0x00 = "sem Report ID" (o hidapi remove esse byte) + 64 bytes úteis, como na captura
        n = dev.write(MCHOSE_CMD + bytes(60))
        if n < 0:
            erro = dev.error() if hasattr(dev, "error") else ""
            print(f"[MCHOSE] write falhou: {erro}")
            return BatteryReading(responding=False)

        recebeu = False
        limite = time.monotonic() + 0.5
        while time.monotonic() < limite:
            resp = bytes(dev.read(64, 100))
            if not resp:
                continue
            recebeu = True
            if resp[:len(MCHOSE_CMD)] == MCHOSE_CMD:   # eco do próprio comando (por segurança)
                continue
            pct = parse_mchose(resp)
            if pct is not None:
                return BatteryReading(percent=pct)
        # recebeu = chegaram relatórios, mas nenhum era a resposta; False = silêncio total
        return BatteryReading(responding=recebeu)
    except Exception as e:
        print(f"[MCHOSE] Erro: {e}")
        return BatteryReading(responding=False)
    
# --------------------------------------------------------------------------
# Driver: GameSir (Cyclone 2)
# --------------------------------------------------------------------------
GAMESIR_CMD = bytes([0x0F, 0xF2, 0x00] + [0x00] * 61) # 64 bytes totais

@register("gamesir")
def read_gamesir(dev) -> BatteryReading:
    try:
        _drenar(dev)
        
        # O GameSir pode precisar de até 3 tentativas para acordar e mandar o dado real
        for tentativa in range(3):
            n = dev.write(GAMESIR_CMD)
            if n < 0:
                erro = dev.error() if hasattr(dev, "error") else ""
                print(f"[GameSir] write falhou: {erro}")
                return BatteryReading(responding=False)
            
            limite = time.monotonic() + 0.3
            while time.monotonic() < limite:
                resp = bytes(dev.read(64, 100))
                if not resp:
                    continue
                
                # Report ID do status do GameSir
                if resp[0] == 0x12:
                    pct = resp[36]
                    # Se pct for 0, pode ser o chip acordando. Tentamos de novo.
                    if pct > 0 or tentativa == 2:
                        # Byte 35 é o status de carga (1 ou mais = carregando)
                        charging = bool(resp[35]) if resp[35] < 255 else None
                        return BatteryReading(percent=pct, charging=charging)
            
            time.sleep(0.05) 
            
        return BatteryReading(responding=False)
        
    except Exception as e:
        print(f"[GameSir] Erro: {e}")
        return BatteryReading(responding=False)

# Driver Logitech NÃO registrado de propósito: os bytes do código anterior
# ([0x10, 0xFF, 0x07, ...]) não parecem uma consulta HID++ válida (consulta de registrador
# usa o sub-id 0x81, e o índice 0xFF é o do receptor, não o do mouse) e não vieram de uma
# captura como o do MCHOSE. Valores 0–100 sem significado passariam pela validação.
# Antes de ativar: capturar o app oficial ou seguir a documentação do Solaar e testar.


# --------------------------------------------------------------------------
# Infraestrutura: locks, cache, estado
# --------------------------------------------------------------------------
_locks: dict = {}
_locks_guard = threading.Lock()
_state_lock = threading.Lock()
_ultima: dict = {}           # chave -> (percent, instante)
_falhas: dict = {}           # chave -> timeouts seguidos
_drivers_avisados: set = set()


def _lock_for(chave: str) -> threading.Lock:
    """Um lock por dispositivo: leituras de aparelhos diferentes não se bloqueiam."""
    with _locks_guard:
        return _locks.setdefault(chave, threading.Lock())


def _ordenar_interfaces(infos: list) -> list:
    """Interface 'vendor' (usage_page >= 0xFF00) primeiro; o resto mantém a ordem."""
    return sorted(infos, key=lambda i: 0 if (i.get("usage_page") or 0) >= USAGE_PAGE_VENDOR else 1)


def _ler_bateria(driver_fn, interfaces: list, chave: str) -> BatteryReading:
    """Abre -> lê -> fecha (sempre), sob o lock do aparelho. Tenta mais de uma interface."""
    ultimo = BatteryReading(responding=False)
    with _lock_for(chave):
        for info in interfaces[:MAX_INTERFACES]:
            dev = hid.device()
            try:
                dev.open_path(info["path"])
                leitura = driver_fn(dev)
            except Exception as e:
                print(f"[HID] {chave}: {e}")
                continue
            finally:
                try:
                    dev.close()
                except Exception:
                    pass
            if leitura.percent is not None:
                return leitura
            ultimo = leitura
    return ultimo


def _estado(chave: str, leitura: BatteryReading, db: dict) -> tuple:
    """Devolve (bateria, conectado) aplicando cache e contagem de falhas."""
    agora = time.monotonic()
    with _state_lock:
        if leitura.percent is not None:
            _ultima[chave] = (leitura.percent, agora)
            _falhas[chave] = 0
            return leitura.percent, True

        if not leitura.responding:
            _falhas[chave] = _falhas.get(chave, 0) + 1

        if db.get("offline_on_timeout") and _falhas.get(chave, 0) >= FALHAS_PARA_OFFLINE:
            return None, False

        anterior = _ultima.get(chave)
        percent = anterior[0] if anterior and agora - anterior[1] <= CACHE_TTL_S else None
        return percent, True


def _avisar_driver_ausente(nome_driver: str, device_key: str) -> None:
    if nome_driver not in _drivers_avisados:
        _drivers_avisados.add(nome_driver)
        print(f"[HID] battery_driver '{nome_driver}' ({device_key}) não existe em DRIVERS; bateria indisponível.")


def _montar(db: dict, master_id: str, mode: str, vid: str, pid: str, battery, connected: bool) -> dict:
    if mode == "dongle":
        conexao, tipo = "📡 Wireless 2.4GHz", "Wireless"
    else:
        conexao, tipo = "🔌 USB (Cabo)", db.get("category", "periferico").capitalize()
    return {
        "name": db.get("name", master_id),
        "master_id": master_id,
        "mode": mode,
        "type": tipo,
        "connection": conexao,
        "battery": battery,
        "vendor_id": vid,
        "product_id": pid,
        "icon": "",
        "connected": connected,
        "category": db.get("category", "wireless"),
        "battery_driver": db.get("battery_driver")
    }


# --------------------------------------------------------------------------
# Função que o api.py chama
# --------------------------------------------------------------------------
def get_wireless_devices() -> list[dict]:
    grupos: dict = {}
    try:
        for info in hid.enumerate():
            vid, pid = info["vendor_id"], info["product_id"]
            device_key = f"{vid:04X}_{pid:04X}"
            db = KNOWN_DEVICES.get(device_key)
            if not db:
                continue

            master_id = db.get("master_id", device_key)
            mode = db.get("mode", "dongle")
            if mode not in ("dongle", "cabo"):
                mode = "dongle"

            # (master_id, mode): cabo e dongle do mesmo aparelho são entradas separadas
            g = grupos.setdefault((master_id, mode), {
                "db": db, "key": device_key, "vid": f"{vid:04X}", "pid": f"{pid:04X}", "interfaces": [],
            })
            g["interfaces"].append(info)
    except Exception as e:
        print(f"[HID] Erro ao enumerar: {e}")
        return []

    resultado = []
    for (master_id, mode), g in grupos.items():
        db = g["db"]
        battery, connected = None, True

        nome_driver = db.get("battery_driver")
        if nome_driver:
            driver_fn = DRIVERS.get(nome_driver)
            if driver_fn is None:
                _avisar_driver_ausente(nome_driver, g["key"])
            else:
                chave = f"{master_id}/{mode}"
                leitura = _ler_bateria(driver_fn, _ordenar_interfaces(g["interfaces"]), chave)
                battery, connected = _estado(chave, leitura, db)

        resultado.append(_montar(db, master_id, mode, g["vid"], g["pid"], battery, connected))
    return resultado


# --------------------------------------------------------------------------
# Diagnóstico: python hid_battery.py [--interfaces]
# --------------------------------------------------------------------------
if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace") # type: ignore
    except Exception:
        pass

    if "--interfaces" in sys.argv:
        for info in hid.enumerate():
            key = f'{info["vendor_id"]:04X}_{info["product_id"]:04X}'
            if key in KNOWN_DEVICES:
                print(f'{key}  interface={info.get("interface_number")}  '
                      f'usage_page=0x{(info.get("usage_page") or 0):04X}  usage=0x{(info.get("usage") or 0):04X}  '
                      f'{KNOWN_DEVICES[key].get("name", "")}')
    else:
        for d in get_wireless_devices():
            bat = f'{d["battery"]}%' if d["battery"] is not None else "N/A"
            estado = "CONECTADO" if d["connected"] else "desconectado"
            print(f'{d["name"]:<24} {d["mode"]:<7} {estado:<13} bateria: {bat}')