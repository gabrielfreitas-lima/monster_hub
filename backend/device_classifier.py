"""
device_classifier.py
Inteligência de classificação de periféricos.
"""

import re

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

GENERICAS = {"audio", "periferico", "bluetooth", "outro"}

PALAVRAS_NOME = [
    ("controle",     ["controller", "controle", "gamepad", "joystick", "dualsense",
                      "dualshock", "xbox", "joy-con", "joycon", "8bitdo"]),
    # JBL agora é reconhecido prioritariamente como fone
    ("fone",         ["fone", "headset", "headphone", "buds", "airpods", "earbuds",
                      "earphone", "wh-1000", "wf-1000", "jbl tune", "jbl live", 
                      "jbl quantum", "jbl"]),
    ("caixa de som", ["echo", "alexa", "speaker", "soundbar", "caixa", "boombox",
                      "jbl go", "jbl flip", "jbl charge", "homepod"]),
    ("teclado",      ["keyboard", "teclado"]),
    ("mouse",        ["mouse"]),
    ("relogio",      ["watch", "relogio", "relógio", "smartband", "mi band"]),
    ("celular",      ["iphone", "galaxy", "pixel", "phone", "celular", "smartphone"]),
    ("computador",   ["notebook", "laptop", "desktop", "macbook"]),
]

POR_CLASSE_PNP = {
    "Mouse": "mouse",
    "Keyboard": "teclado",
    "AudioEndpoint": "audio",
    "MEDIA": "audio",
}

def rotulo(categoria: str) -> str:
    return CATEGORIAS.get(categoria, CATEGORIAS["outro"])[0]

def emoji(categoria: str) -> str:
    return CATEGORIAS.get(categoria, CATEGORIAS["outro"])[1]

def categoria_por_cod(raw: int | None) -> str | None:
    if raw is None: return None
    major = (raw >> 8) & 0x1F
    minor = (raw >> 2) & 0x3F

    if major == 4:  # Áudio/Vídeo
        if minor in (1, 2, 6): return "fone"
        if minor in (5, 7, 8): return "caixa de som"
        return "audio"
    if major == 5:  # Periférico (HID)
        if raw & 0x40: return "teclado"
        if raw & 0x80: return "mouse"
        tipo = (raw >> 2) & 0x0F
        if tipo in (1, 2): return "controle"
        return "periferico"
    if major == 2: return "celular"
    if major == 1: return "computador"
    if major == 7: return "relogio"
    return None

def categoria_por_appearance(raw: int | None) -> str | None:
    if not raw: return None
    categoria, sub = raw >> 6, raw & 0x3F
    if categoria == 15:
        return {1: "teclado", 2: "mouse", 3: "controle", 4: "controle"}.get(sub, "periferico")
    if categoria == 1: return "celular"
    if categoria == 2: return "computador"
    if categoria == 3: return "relogio"
    return None

def categoria_por_hardware_ids(ids: list | None) -> str | None:
    for hw in ids or []:
        h = (hw or "").upper()
        if "HID_DEVICE_SYSTEM_MOUSE" in h: return "mouse"
        if "HID_DEVICE_SYSTEM_KEYBOARD" in h: return "teclado"
        if "HID_DEVICE_SYSTEM_GAME" in h: return "controle"
    return None

def categoria_por_nome(nome: str | None) -> str | None:
    n = (nome or "").lower()
    if not n: return None
    for categoria, palavras in PALAVRAS_NOME:
        for p in palavras:
            if re.search(r"(?<![a-z0-9])" + re.escape(p), n):
                return categoria
    return None

def classificar(nome=None, cod=None, appearance=None, hardware_ids=None,
                pnp_class=None, fallback="outro") -> str:
    pistas = [
        categoria_por_cod(cod),
        categoria_por_appearance(appearance),
        categoria_por_hardware_ids(hardware_ids),
        categoria_por_nome(nome),
        POR_CLASSE_PNP.get(pnp_class or ""),
    ]
    pistas = [p for p in pistas if p]

    for p in pistas:
        if p not in GENERICAS:
            return p
    for p in pistas:
        if p != "outro":
            return p
    return fallback