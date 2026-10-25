# MONSTER HUB 🖥️🖱️🎧🎮

[![Versão Pré-Alpha](https://img.shields.io/github/v/release/gabrielfreitas-lima/monster_hub?include_prereleases&style=for-the-badge&label=Baixar%20Versão)](https://github.com/gabrielfreitas-lima/monster_hub/releases)


> **Status do Projeto:** 🚧 **v0.1.4 (Pré-Alpha)** 🚧
> Esta é a quarta versão do aplicativo. O foco continua sendo o mapeamento e suporte dos periféricos utilizados pelo autor (Darmoshark M3, AULA F75, MCHOSE V9 PRO, JBL TUNE520BT e GameSir Cyclone 2). Novos dispositivos serão adicionados nas próximas atualizações.

Um aplicativo desktop minimalista para monitorar a conexão e a bateria de periféricos (USB, Bluetooth e Wireless 2.4GHz) no Windows.

## ✨ Funcionalidades Atuais
*   **Detecção automática** de mouses, teclados, fones, controles e caixas de som.
*   **Leitura de bateria híbrida:** 
    *   Via HID raw para dispositivos Wireless 2.4GHz (ex: MCHOSE e GameSir Cyclone 2).
    *   Via PnP do Windows para dispositivos Bluetooth (ex: JBL TUNE520BT).
*   **Agrupamento Inteligente (Master ID):** Une múltiplas interfaces do mesmo hardware (ex: controle com cabo, dongle e Bluetooth ao mesmo tempo) em um único cartão visual.
*   **Sistema Anti-Fantasma (V3):** O backend cruza as informações do banco de dados e do histórico para garantir que dispositivos desligados (mas com dongle ativo) apareçam corretamente na tela, sem conexões falsas (ex: "Cabo" em um controle Wireless).
*   **Diferenciação de modo (Cabo vs Wireless)** para dispositivos que expõem diferentes VID/PIDs (ex: Teclado AULA F75 e GameSir).
*   **Splash Screen Temática:** Tela de carregamento com animação, cantos arredondados e que se adapta automaticamente ao tema escolhido pelo usuário.
*   **Interface minimalista e polida:** 4 temas (Escuro, Claro, Creme/Roxo e Cyberpunk Neon) gerenciados por arquivo CSS separado, e 2 idiomas (PT/EN).
*   **Animações Fluidas:** Atualização automática a cada 5 segundos com *DOM Diffing* (sem piscar a tela ou resetar o hover) e animações de refresh contínuas e suaves.

## ⚠️ Limitações Conhecidas (Escopo da Pré-Alpha)
*   **Múltiplos Controles Idênticos:** Se dois controles GameSir iguais forem conectados simultaneamente, o app agrupará ambos em um único cartão. O suporte a múltiplos dispositivos do mesmo modelo requer o uso do Instance ID (planejado para v0.2.0).
*   **Periféricos com chave física (Darmoshark):** O hardware mantém as interfaces de cabo e dongle ativas com o mesmo VID/PID. O app exibe apenas o nome e ícone, ocultando o modo de conexão para evitar informações erradas.
*   **Fone Desligado no Cabo:** O chip USB do fone (MCHOSE) não ativa quando ele está desligado, então o app não o detecta no cabo.
*   **Status do Fone Desligado (MCHOSE):** O dongle continua ativo no Windows. O app usa o timeout do driver de bateria (1 falha) para movê-lo rapidamente para a aba de desconectados.
*   **Drivers de Bateria:** O app lê a bateria do MCHOSE, GameSir e fones Bluetooth padrão (via PnP). O suporte a Logitech (HID++) e outras marcas requer engenharia reversa (Wireshark) para ser ativado no `hid_battery.py`.

## 🏗️ Arquitetura
*   **Backend (Python + FastAPI):** Detectores assíncronos (`usb_detector`, `bt_detector`, `hid_battery`, `gamepad_detector`). Utiliza padrão **Strategy** para a leitura de bateria, **Master ID** para agrupar interfaces duplicadas e regras de **Fallback** no `api.py` para correção de dados.
*   **Frontend (Electron + JS):** Renderização local com *cache* em memória, *DOM Diffing* para atualizações sem cintilação, temas dinâmicos via CSS Variables (separados em `themes.css`) e animações suaves.

---

## 🚀 Como rodar em ambiente de desenvolvimento

### 1. Backend (Terminal 1)
```bash
cd backend
python -m venv venv
# Ative o ambiente virtual (Windows):
.\venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn api:app --reload
```
O servidor rodará em `http://127.0.0.1:8000`.

### 2. Frontend (Terminal 2)
```bash
cd frontend
npm install
npm start
```

---

## 📦 Como gerar o executável (.exe final)

### 1. Compilar o Backend (PyInstaller)
Sempre que alterar arquivos Python, você precisa recompilar:
```bash
cd backend
Remove-Item -Recurse -Force dist, build
pyinstaller --noconfirm --onedir --windowed --clean --name "backend" --hidden-import gamepad_detector --hidden-import pygame --hidden-import uvicorn.logging --hidden-import winrt.windows.devices.radios servidor.py
```

### 2. Compilar o Frontend (Electron Builder)
Sempre que alterar o visual ou empacotar uma nova versão:
```bash
cd frontend
npm run build
```
O instalador final será gerado dentro da pasta `frontend/dist`.

---

## 👨‍💻 Desenvolvido por:
Gabriel Freitas ([@gabrielfreitas-lima](https://github.com/gabrielfreitas-lima))