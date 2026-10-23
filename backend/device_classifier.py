"""
device_classifier.py
Inteligência de classificação de periféricos.

NOTA PARA O TIME DE DESENVOLVIMENTO:
Este arquivo não interage com o hardware. Ele recebe "pistas" (ID, nome, classe) 
que outros arquivos (bt_detector, usb_detector) já coletaram, e devolve a 
categoria correta (mouse, teclado, fone, etc).

A ordem de confiança das pistas é:
1. Class of Device (Bluetooth Clássico) - Informação oficial do hardware
2. Appearance (Bluetooth LE) - Informação oficial do hardware
3. HardwareIDs do Windows (ex: HID_DEVICE_SYSTEM_MOUSE)
4. Palavras no nome (ex: "Galaxy Buds" contém "buds", logo é fone)
5. Classe PnP do Windows (Mouse, Keyboard, AudioEndpoint)
"""

import re

# Dicionário de Categorias (rótulo, emoji)
CATEGORIAS = {
    "mouse":        ("Mouse", "🖱️"),
    "teclado":      ("Teclado", "⌨️"),
    "fone":         ("Fone", "🎧"),
    "caixa de som": ("Caixa de som", "🔊"),
    "audio":        ("Áudio", "🔊"),
    "controle":     ("Controle", "🎮"),
    "celular":      ("Celular", "📱"),
    "computador":   ("Computador", "💻"),
    "relogio":      ("Relógio", "⌚"),
    "periferico":   ("Periférico", "🔌"),
    "bluetooth":    ("Bluetooth", "📶"),
    "outro":        ("Outro", "🔌"),
}

# Categorias vagas: se a primeira pista retornar isso, tentamos refinar com a próxima
GENERICAS = {"audio", "periferico", "bluetooth", "outro"}

# Palavras no nome (Ordem importa: "Galaxy Buds" é fone, não celular)
PALAVRAS_NOME = [
    ("controle",     ["controller", "controle", "gamepad", "joystick", "dualsense",
                      "dualshock", "xbox", "joy-con", "joycon", "8bitdo"]),
    ("fone",         ["fone", "headset", "headphone", "buds", "airpods", "earbuds",
                      "earphone", "wh-1000", "wf-1000"]),
    ("caixa de som", ["echo", "alexa", "speaker", "soundbar", "caixa", "boombox",
                      "jbl", "homepod"]),
    ("teclado",      ["keyboard", "teclado"]),
    ("mouse",        ["mouse"]),
    ("relogio",      ["watch", "relogio", "relógio", "smartband", "mi band"]),
    ("celular",      ["iphone", "galaxy", "pixel", "phone", "celular", "smartphone"]),
    ("computador",   ["notebook", "laptop", "desktop", "macbook"]),
]

# Classe PnP do Windows
POR_CLASSE_PNP = {
    "Mouse": "mouse",
    "Keyboard": "teclado",
    "AudioEndpoint": "audio",
    "MEDIA": "audio",
}

def rotulo(categoria: str) -> str:
    """Retorna o nome legível da categoria."""
    return CATEGORIAS.get(categoria, CATEGORIAS["outro"])[0]

def emoji(categoria: str) -> str:
    """Retorna o emoji da categoria (usado apenas nos testes de terminal)."""
    return CATEGORIAS.get(categoria, CATEGORIAS["outro"])[1]

# --------------------------------------------------------------------------
# Pistas Individuais
# --------------------------------------------------------------------------
def categoria_por_cod(raw: int | None) -> str | None:
    """
    Lê o 'Class of Device' do Bluetooth Clássico. 
    É um número em binário onde os bits informam o tipo de aparelho.
    """
    if raw is None: return None
    
    # Deslocamento de bits para extrair Major e Minor Device Class
    major = (raw >> 8) & 0x1F
    minor = (raw >> 2) & 0x3F

    if major == 4:  # Áudio/Vídeo
        if minor in (1, 2, 6): return "fone"          # Headset, Hands-free, Headphones
        if minor in (5, 7, 8): return "caixa de som"  # Loudspeaker, Portable Audio
        return "audio"
        
    if major == 5:  # Periférico (HID)
        if raw & 0x40: return "teclado"
        if raw & 0x80: return "mouse"
        tipo = (raw >> 2) & 0x0F
        if tipo in (1, 2): return "controle"         # Joystick, Gamepad
        return "periferico"
        
    if major == 2: return "celular"
    if major == 1: return "computador"
    if major == 7: return "relogio"
    return None

def categoria_por_appearance(raw: int | None) -> str | None:
    """Lê o 'Appearance' do Bluetooth LE (padrão para dispositivos BLE)."""
    if not raw: return None
    categoria, sub = raw >> 6, raw & 0x3F
    
    if categoria == 15:  # Generic HID
        return {1: "teclado", 2: "mouse", 3: "controle", 4: "controle"}.get(sub, "periferico")
    if categoria == 1: return "celular"
    if categoria == 2: return "computador"
    if categoria == 3: return "relogio"
    return None

def categoria_por_hardware_ids(ids: list | None) -> str | None:
    """Lê os HardwareIDs do Windows (ex: HID_DEVICE_SYSTEM_MOUSE)."""
    for hw in ids or []:
        h = (hw or "").upper()
        if "HID_DEVICE_SYSTEM_MOUSE" in h: return "mouse"
        if "HID_DEVICE_SYSTEM_KEYBOARD" in h: return "teclado"
        if "HID_DEVICE_SYSTEM_GAME" in h: return "controle"
    return None

def categoria_por_nome(nome: str | None) -> str | None:
    """Adivinha a categoria analisando palavras no nome do aparelho."""
    n = (nome or "").lower()
    if not n: return None
    
    for categoria, palavras in PALAVRAS_NOME:
        for p in palavras:
            # O regex garante que "buds" case com "Galaxy Buds2", mas não case com "abc"
            if re.search(r"(?<![a-z0-9])" + re.escape(p), n):
                return categoria
    return None

# --------------------------------------------------------------------------
# Função Principal
# --------------------------------------------------------------------------
def classificar(nome=None, cod=None, appearance=None, hardware_ids=None,
                pnp_class=None, fallback="outro") -> str:
    """
    Testa todas as pistas na ordem de confiança e retorna a categoria mais específica.
    """
    pistas = [
        categoria_por_cod(cod),
        categoria_por_appearance(appearance),
        categoria_por_hardware_ids(hardware_ids),
        categoria_por_nome(nome),
        POR_CLASSE_PNP.get(pnp_class or ""),
    ]
    pistas = [p for p in pistas if p]

    # Retorna a primeira pista que for específica (ignora "audio", "periferico" vago)
    for p in pistas:
        if p not in GENERICAS:
            return p
            
    # Se todas as pistas forem vagas, retorna a melhor que encontramos
    for p in pistas:
        if p != "outro":
            return p
            
    return fallback

# --------------------------------------------------------------------------
# Teste rápido: python device_classifier.py
# --------------------------------------------------------------------------
if __name__ == "__main__":
    print("Testando o Classificador de Dispositivos...\n")
    exemplos = [
        ("Echo Dot-5AH",   dict(nome="Echo Dot-5AH", cod=0x240414)),
        ("Fone (CoD)",     dict(nome="THERIVER", cod=0x240404)),
        ("Teclado BT",     dict(nome="K380", cod=0x002540)),
        ("Mouse BT",       dict(nome="MX Master", cod=0x002580)),
        ("Gamepad BT",     dict(nome="Wireless Controller", cod=0x002508)),
        ("Celular",        dict(nome="Redmi", cod=0x5A020C)),
        ("Só nome: buds",  dict(nome="Galaxy Buds2")),
        ("HID mouse",      dict(hardware_ids=["HID_DEVICE_SYSTEM_MOUSE"])),
        ("Áudio vago+nome", dict(nome="Alexa", cod=0x240400)),
        ("Desconhecido",   dict(nome="XYZ123")),
    ]
    for titulo, kw in exemplos:
        c = classificar(**kw, fallback="bluetooth")
        print(f"{titulo:<18} -> {c:<13} {emoji(c)} {rotulo(c)}")