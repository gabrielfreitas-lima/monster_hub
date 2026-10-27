# 🗺️ ROADMAP: MONSTER HUB

## 🚀 v0.2.0 — Device Control (Read/Write)
**Objetivo:** Transformar o Monster Hub de um monitor passivo para um controlador ativo de hardware (ajuste de volume, EQ, ANC, etc).

### 🕵️ 1. Engenharia Reversa (A Captura)
*   **Ferramenta:** Wireshark + USBPcap.
*   **Alvo Inicial:** Testar um toggle simples (ex: *AI Noise Reduction* ou *Audio Brightening*) do MCHOSE V9 PRO.
*   **Filtros Mágicos do Wireshark:**
    *   `usb.idVendor == 0x291D && usb.src == "host"` (para ver o que o PC envia).
    *   Focar em pacotes `URB_CONTROL out` com `Request = SET_REPORT`.
    *   Observar a `bInterfaceNumber` (provavelmente será a mesma de bateria, a `0xfff0`).
*   **Ação:** Capturar o pacote de "Ligar" e "Desligar" e isolar o byte que muda.

### 🏗️ 2. Arquitetura do Backend (Temporária)
*   **Novo Arquivo:** Criar o `backend/hid_control.py` (separado do `hid_battery.py`).
*   **Padrão de Projeto:** Usar a mesma arquitetura de plugins (`@register_control("mchose")`).
*   **Novas Rotas no `api.py`:**
    *   Criar uma rota `POST /device/control`.
    *   **Contrato do Payload:**
        ```json
        {
          "master_id": "MCHOSE_V9",
          "param": "ai_noise_reduction",
          "value": true // ou 80, se for volume
        }
        ```

### 🎨 3. Arquitetura do Frontend (Temporária)
*   **Interação:** Adicionar um evento de clique no cartão do dispositivo (`.card`).
*   **Nova Tela:** Criar um painel/modal que abre ao clicar no cartão (com sliders e toggles).

---

## 🦀 v1.0.0 — A Grande Refatoração (Migração para Rust)
**Objetivo:** Abandonar a arquitetura Electron + Python para deixar o aplicativo incrivelmente leve, rápido e nativo.

*   **O Salto Arquitetural:** Migrar o frontend do Electron para o **Tauri** (que usa a WebView nativa do Windows).
*   **Backend Nativo:** Reescrever toda a lógica de detecção e controle (atualmente em Python/FastAPI) para **Rust puro**.
*   **Substituição de Dependências Python por Crates Rust:**
    *   `hidapi` (Python) -> crate `hidapi` (Rust).
    *   `wmi` (Python) -> crate `windows` (para chamadas WMI e WinRT).
    *   `bleak` (Python) -> crate `btleplug` (para Bluetooth).
    *   `FastAPI` -> Comunicação direta via IPC nativo do Tauri (sem necessidade de servidor HTTP local).
*   **Ganhos Esperados:** 
    *   Tamanho do instalador: De ~150MB para ~5MB.
    *   Uso de RAM: De ~300MB para < 50MB.
    *   Inicialização: De 3 segundos para menos de 1 segundo.