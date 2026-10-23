"""
gamepad_detector.py
Especialista em Controles de Videogame (GameSir, Xbox, Sony, etc.).

NOTA PARA O TIME DE DESENVOLVIMENTO:
O Windows não tem uma API nativa que diga "este controle está via cabo ou dongle".
Para resolver isso, o código usa "Perfis de VID/PID":
1. O usuário conecta o controle no cabo e roda `python gamepad_detector.py --registrar`.
2. O usuário conecta o dongle e roda novamente.
3. O script salva os VID/PID no arquivo 'controles_registrados.json'.
4. Na execução normal, o código cruza os VID/PID presentes no Windows com o JSON 
   para saber se o controle está conectado no cabo, no dongle, ou se o dongle está 
   plugado mas o controle está desligado.
"""

import io
import json
import os
import re
import sys
import wmi
import pythoncom

# Caminho do banco de dados de perfis de controle
REGISTRO_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "controles_registrados.json"
)

# Tipos de conexão mapeados
CONEXOES = {
    "cabo": "🔌 USB (Cabo)",
    "dongle": "📡 Wireless 2.4GHz (Dongle)",
    "dongle_aguardando": "📡 Wireless 2.4GHz (Dongle)", # Dongle plugado, controle desligado
}

# Perfis que já sabemos (exemplo com GameSir)
PERFIS_PADRAO = {
    "3537:1053": {"nome": "Controle GameSir", "conexao": "cabo"},
    "3537:100B": {"nome": "Controle GameSir", "conexao": "dongle"},
    "3537:0575": {"nome": "Controle GameSir", "conexao": "dongle_aguardando"},
}

# Nomes de fabricantes conhecidos para "adivinhar" o nome se não estiver registrado
MARCAS = {
    "3537": "GameSir", "045E": "Microsoft", "054C": "Sony", "057E": "Nintendo",
    "2DC8": "8BitDo", "0F0D": "HORI", "0E6F": "PDP",
}

# Regex para encontrar informações nos IDs do Windows
RE_VIDPID = re.compile(r"VID_([0-9A-F]{4})&PID_([0-9A-F]{4})", re.I)
RE_SERIAL = re.compile(r"^USB\\VID_[0-9A-F]{4}&PID_[0-9A-F]{4}\\([^\\&]+)$", re.I)
RE_IG = re.compile(r"&IG_\d+", re.I)
RE_NOME_CONTROLE = re.compile(
    r"controlador de jogo|game controller|gamepad|joystick|xbox 360|xbox one|xinput", re.I
)
USO_HID_GAMEPAD = ("UP:0001_U:0005", "UP:0001_U:0004")  # gamepad, joystick

# --------------------------------------------------------------------------
# Gerenciamento de Perfis
# --------------------------------------------------------------------------
def carregar_perfis() -> dict:
    """Carrega os perfis padrão e os que o usuário registrou no JSON."""
    perfis = {k.upper(): dict(v) for k, v in PERFIS_PADRAO.items()}
    try:
        with open(REGISTRO_PATH, "r", encoding="utf-8") as f:
            extra = json.load(f)
        for chave, v in extra.items():
            if isinstance(v, dict) and v.get("nome") and v.get("conexao") in CONEXOES:
                perfis[chave.upper()] = v
    except Exception:
        pass
    return perfis

def _salvar_registro(chave: str, nome: str, conexao: str) -> None:
    """Salva um novo controle descoberto no JSON."""
    try:
        with open(REGISTRO_PATH, "r", encoding="utf-8") as f:
            dados = json.load(f)
    except Exception:
        dados = {}
    dados[chave.upper()] = {"nome": nome, "conexao": conexao}
    with open(REGISTRO_PATH, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

def _nome_padrao(vid: str) -> str:
    marca = MARCAS.get(vid)
    return f"Controle {marca}" if marca else f"Controle {vid}"

# --------------------------------------------------------------------------
# Análise Lógica
# --------------------------------------------------------------------------
def _e_controle(e: dict) -> bool:
    """Verifica se um dispositivo do Windows tem características de controle."""
    if (e.get("pnp_class") or "") == "XnaComposite": return True
    if RE_IG.search(e.get("device_id") or ""): return True
    ids = " ".join(e.get("hardware_ids") or []).upper()
    if any(u in ids for u in USO_HID_GAMEPAD): return True
    return bool(RE_NOME_CONTROLE.search(e.get("name") or ""))

def _escanear(entradas: list[dict]) -> dict:
    """Agrupa as entradas do Windows por (VID, PID)."""
    presentes = {}
    for e in entradas:
        did = e.get("device_id") or ""
        up = did.upper()
        if not (up.startswith("USB\\") or up.startswith("HID\\")):
            continue
        m = RE_VIDPID.search(did)
        if not m: continue
        par = (m.group(1).upper(), m.group(2).upper())
        
        info = presentes.setdefault(par, {"controle": False, "serial": None, "nome": None})
        if _e_controle(e):
            info["controle"] = True
            info["nome"] = info["nome"] or e.get("name")
        s = RE_SERIAL.match(did)
        if s: info["serial"] = s.group(1)
    return presentes

def analisar(entradas: list[dict], perfis: dict) -> list[dict]:
    """Cruza os dados do Windows com os perfis para saber o tipo de conexão."""
    presentes = _escanear(entradas)
    grupos = {}

    for (vid, pid), info in presentes.items():
        perfil = perfis.get(f"{vid}:{pid}")
        if not perfil and not info["controle"]:
            continue # Ignora o que não é controle
            
        nome = perfil["nome"] if perfil else _nome_padrao(vid)
        conexao = perfil["conexao"] if perfil else "desconhecida"
        
        g = grupos.setdefault(nome, {"pares": {}})
        g["pares"].setdefault(conexao, (vid, pid))

    resultado = []
    for nome, g in grupos.items():
        pares = g["pares"]
        
        # Lógica de prioridade de conexão
        if "cabo" in pares:
            texto, conectado = CONEXOES["cabo"], True
            if "dongle" in pares: texto += " + Wireless"
        elif "dongle" in pares:
            texto, conectado = CONEXOES["dongle"], True
        elif "dongle_aguardando" in pares:
            # O dongle está plugado, mas o controle está desligado
            texto, conectado = CONEXOES["dongle_aguardando"], False
        else:
            texto, conectado = "🎮 USB (Modo desconhecido)", True

        # Pega o VID/PID principal para o Frontend
        vid, pid = list(pares.values())[0]

        resultado.append({
            "name": nome,
            "master_id": f"GAMEPAD_{vid}_{pid}",
            "type": "Gamepad",
            "connection": texto,
            "battery": None,
            "vendor_id": vid,
            "product_id": pid,
            "icon": "", # O Frontend resolve o ícone
            "connected": conectado,
            "category": "controle",
        })
    return resultado

# --------------------------------------------------------------------------
# Leitura do Windows (WMI)
# --------------------------------------------------------------------------
def _ler_entradas_wmi() -> list[dict]:
    """Lê o hardware do Windows via WMI."""
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
    """
    Função principal chamada pelo api.py.
    Lê o WMI, carrega os perfis e retorna a lista de controles padronizada.
    """
    try:
        entradas = _ler_entradas_wmi()
        return analisar(entradas, carregar_perfis())
    except Exception as e:
        print(f"[Gamepad] Erro ao ler controles: {e}")
        return []

# --------------------------------------------------------------------------
# Modo de Registro Interativo (para rodar no terminal)
# --------------------------------------------------------------------------
def registrar() -> None:
    """Permite cadastrar um novo controle no JSON rodando o arquivo direto no terminal."""
    presentes = _escanear(_ler_entradas_wmi())
    vids = {vid for (vid, _), i in presentes.items() if i["controle"]}
    candidatos = [(par, i) for par, i in sorted(presentes.items()) if i["controle"] or par[0] in vids]
    
    if not candidatos:
        print("Nenhum controle detectado. Conecte o controle e tente de novo.")
        return

    print("\nDispositivos encontrados:")
    for n, (par, i) in enumerate(candidatos, 1):
        tipo = "controle" if i["controle"] else "mesmo fabricante"
        print(f" [{n}] {par[0]}:{par[1]}  {tipo:<17} serial: {i['serial'] or '-'}  {i['nome'] or ''}")

    while True:
        escolha = input("\nNúmero do item a registrar (Enter para sair): ").strip()
        if not escolha: return
        if not escolha.isdigit() or not (1 <= int(escolha) <= len(candidatos)):
            print("Número inválido."); continue
            
        (vid, pid), _ = candidatos[int(escolha) - 1]
        padrao = _nome_padrao(vid)
        nome = input(f"Nome do controle [{padrao}]: ").strip() or padrao

        print("Como este item aparece?")
        opcoes = list(CONEXOES.items())
        for n, (_, desc) in enumerate(opcoes, 1):
            print(f"  {n}) {desc}")
            
        c = input("Opção: ").strip()
        if not c.isdigit() or not (1 <= int(c) <= len(opcoes)):
            print("Opção inválida."); continue
            
        conexao = opcoes[int(c) - 1][0]
        _salvar_registro(f"{vid}:{pid}", nome, conexao)
        print(f"Registrado: {vid}:{pid} -> {nome} ({conexao}). Salvo em {REGISTRO_PATH}")

# --------------------------------------------------------------------------
# Teste Rápido: python gamepad_detector.py | --registrar
# --------------------------------------------------------------------------
if __name__ == "__main__":
    # Correção para o Pylance: verifica se é um stream de texto válido antes de reconfigurar
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if "--registrar" in sys.argv:
        registrar()
    else:
        achados = get_gamepads()
        if not achados: 
            print("Nenhum controle detectado.")
        for g in achados:
            estado = "CONECTADO" if g["connected"] else "desconectado"
            print(f'{g["name"]:<22} {estado:<13} {g["connection"]}  ({g["vendor_id"]}:{g["product_id"]})')