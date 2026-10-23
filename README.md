# Peripheral Monitor 🖥️🖱️🎧

> **Status do Projeto:** 🚧 **v0.1.0 (Pré-Alpha)** 🚧
> Esta é a primeira versão do aplicativo. O foco inicial foi o mapeamento e suporte dos periféricos utilizados pelo autor (Darmoshark M3, AULA F75, MCHOSE V9 PRO). Novos dispositivos serão adicionados nas próximas atualizações.

Um aplicativo desktop minimalista para monitorar a conexão e a bateria de periféricos (USB, Bluetooth e Wireless 2.4GHz) no Windows.

## ✨ Funcionalidades Atuais
*   **Detecção automática** de mouses, teclados, fones e caixas de som.
*   **Leitura de bateria** para dispositivos 2.4GHz com protocolos mapeados (MCHOSE) e Bluetooth (BLE).
*   **Diferenciação de modo (Cabo vs Wireless)** para dispositivos que expõem diferentes VID/PIDs (ex: Teclado AULA F75).
*   **Histórico de conexão** com selo "NOVO" (2 minutos) e data da última conexão.
*   **Interface minimalista** com 3 temas (Escuro, Claro e Creme/Roxo) e 2 idiomas (PT/EN).
*   **Atualização automática** a cada 5 segundos, troca de abas instantânea e animação de refresh.

## ⚠️ Limitações Conhecidas (Escopo da Pré-Alpha)
*   **Periféricos com chave física teimosa (Darmoshark):** O hardware mantém as interfaces de cabo e dongle ativas ao mesmo tempo com o mesmo VID/PID. O app exibe apenas o nome e ícone, ocultando o modo de conexão.
*   **Fone Desligado no Cabo:** O chip USB do fone (MCHOSE) não ativa quando ele está desligado, então o app não o detecta no cabo.
*   **Status do Fone Desligado (MCHOSE):** O dongle continua ativo no Windows. O app usa o timeout do driver de bateria (1 falha) para movê-lo rapidamente para a aba OFF.
*   **Filtro de Bateria:** O app lê a bateria apenas do MCHOSE. O suporte a Logitech e outras marcas está preparado na arquitetura (`hid_battery.py`), mas precisa de engenharia reversa (Wireshark) para ser ativado.

## 🏗️ Arquitetura
*   **Backend (Python + FastAPI):** Detectores assíncronos (`usb_detector`, `bt_detector`, `hid_battery`, `gamepad_detector`). Utiliza padrão **Strategy** para a leitura de bateria e **Master ID** para agrupar interfaces duplicadas.
*   **Frontend (Electron + JS):** Renderização local com cache em memória, temas dinâmicos via CSS Variables e animações suaves.

## 🚀 Como rodar em ambiente de desenvolvimento

### 1. Backend (Terminal 1)
```bash
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn api:app --reload