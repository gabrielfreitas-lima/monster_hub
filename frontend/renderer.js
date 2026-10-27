/**
 * renderer.js
 */

const translations = {
  pt: {
    nav_connected: "CONECTADOS", nav_off: "OFF",
    settings_title: "Configurações", language_label: "Idioma", theme_label: "Tema",
    theme_dark: "🌙 Escuro", theme_light: "☁️ Claro", theme_cyberpunk: "🌆 Cyberpunk",
    searching: "Sincronizando periféricos...", 
    empty_connected: "Nenhum periférico conectado.",
    empty_off: "Nenhum periférico desconectado.", 
    error_backend: "Falha de Conexão",
    error_desc: "Não foi possível se comunicar com o serviço local do Monster Hub. Verifique se o backend está em execução.",
    btn_retry: "Tentar Novamente",
    cable: "Cabo", no_battery: "Sem bateria", last_seen: "Última conexão:", new_badge: "NOVO"
  },
  en: {
    nav_connected: "CONNECTED", nav_off: "OFF",
    settings_title: "Settings", language_label: "Language", theme_label: "Theme",
    theme_dark: "🌙 Dark", theme_light: "☁️ Light", theme_cyberpunk: "🌆 Cyberpunk",
    searching: "Synchronizing peripherals...", 
    empty_connected: "No peripherals connected.",
    empty_off: "No peripherals disconnected.", 
    error_backend: "Connection Failed",
    error_desc: "Could not communicate with the Monster Hub local service. Please check if the backend is running.",
    btn_retry: "Try Again",
    cable: "Cable", no_battery: "No battery", last_seen: "Last connection:", new_badge: "NEW"
  }
};

const ICONS = {
  fone: "&#xE95B;", audio: "&#xE767;", "caixa de som": "&#xE767;",
  teclado: "&#xE765;", mouse: "&#xE962;", celular: "&#xE8EA;",
  computador: "&#xE7F4;", controle: "&#xE7FC;", periferico: "&#xE8B7;", padrao: "&#xE8B7;"
};

const KEYWORDS = [
  { cat: "fone", words: ["fone", "headset", "headphone", "gaming", "audio"] },
  { cat: "teclado", words: ["teclado", "keyboard"] },
  { cat: "mouse", words: ["mouse"] },
  { cat: "controle", words: ["controle", "gamepad", "xbox", "playstation", "dualsense"] },
  { cat: "celular", words: ["celular", "phone", "smartphone", "iphone", "android"] },
  { cat: "audio", words: ["caixa de som", "speaker", "alto-falantes"] }
];

let currentView = "connected";
let listaCompleta = []; 
const savedLang = localStorage.getItem("lang");
const systemLang = navigator.language.toLowerCase().startsWith("pt") ? "pt" : "en";
const currentLang = savedLang || systemLang;
let carregando = false;

// 👇 CORREÇÃO 1: Flag para não pular a janela toda hora
let appReadyEnviado = false; 

function applyLanguage() {
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.getAttribute("data-i18n");
    if (translations[currentLang][key]) el.textContent = translations[currentLang][key];
  });
  document.getElementById("language-select").value = currentLang;
}

function applyTheme(theme) {
  document.body.classList.remove("light-mode", "cyberpunk-mode");
  if (theme === "light") document.body.classList.add("light-mode");
  if (theme === "cyberpunk") document.body.classList.add("cyberpunk-mode");
  document.getElementById("theme-select").value = theme;
}

function fmtData(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString(currentLang === "pt" ? "pt-BR" : "en-US", { 
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" 
  });
}

function getDeviceIcon(p) {
  if (p.category) {
    const cat = p.category.toLowerCase().trim();
    if (ICONS[cat]) return ICONS[cat];
  }
  const nome = (p.name || "").toLowerCase();
  for (const item of KEYWORDS) {
    if (item.words.some(w => nome.includes(w))) return ICONS[item.cat];
  }
  if (p.type) {
    if (p.type.includes("Audio") || p.type.includes("MEDIA")) return ICONS.audio;
    if (p.type.includes("Bluetooth")) return "&#xE702;"; 
  }
  return ICONS.padrao; 
}

function getConnectionIcon(connection) {
  if (connection.includes("Bluetooth")) return "&#xE702;";
  if (connection.includes("Wireless")) return "&#xE701;"; 
  return "&#xE71B;"; 
}

function renderCard(p) {
  const icon = getDeviceIcon(p);
  
  const nomeLower = (p.name || "").toLowerCase();
  const isDarmoshark = nomeLower.includes("darmoshark");
  
  const palavrasCaixaFixa = ["echo", "alexa", "speaker", "soundbar", "homepod", "boombox"];
  const isCaixaDeSomFixa = palavrasCaixaFixa.some(w => nomeLower.includes(w));
  const isJBL = nomeLower.includes("jbl");

  const esconderBateria = isDarmoshark || (isCaixaDeSomFixa && !isJBL);
  const esconderConexao = isDarmoshark;

  const connIcon = getConnectionIcon(p.connection || "");
  
  let connText = translations[currentLang].cable;
  if (p.connection && p.connection.includes("Bluetooth")) connText = "Bluetooth";
  if (p.connection && p.connection.includes("Wireless")) connText = "2.4G";

  let batteryHtml = "";
  if (!esconderBateria) {
    if (p.battery != null) {
      batteryHtml = `<div class="detail-item"><span>&#xE83F;</span> ${p.battery}%</div>`;
    } else if (p.connected && !p.connection.includes("Cabo")) {
      batteryHtml = `<div class="detail-item">${translations[currentLang].no_battery}</div>`;
    }
  }

  let connectionHtml = "";
  if (!esconderConexao) {
    connectionHtml = `<div class="detail-item"><span>${connIcon}</span> ${connText}</div>`;
  }

  const statusClass = p.connected ? "" : "status-off";
  const memoriaClass = p.memoria ? "memoria" : "";
  const novoHtml = p.novo ? `<span class="badge-novo">${translations[currentLang].new_badge}</span>` : "";
  const ultimaHtml = (!p.connected && p.ultima_conexao)
    ? `<p class="ultima">${translations[currentLang].last_seen} ${fmtData(p.ultima_conexao)}</p>` 
    : "";

  // 👇 CORREÇÃO 2: Adicionando ID único no cartão (remove espaços e caracteres especiais)
  const safeId = (p.master_id || p.name || "desconhecido").replace(/[^a-zA-Z0-9]/g, "_");

  return `
    <div id="card-${safeId}" class="card ${statusClass} ${memoriaClass}">
      <div class="card-image-container">
        ${p.image ? `<img src="${p.image}" alt="${p.name}">` : `<div class="emoji-icon">${icon}</div>`}
      </div>
      <div class="card-info">
        <div class="card-title" title="${p.name}">${p.name} ${novoHtml}</div>
        <div class="card-details">
          ${batteryHtml}
          ${connectionHtml}
        </div>
        ${ultimaHtml}
      </div>
    </div>`;
}

async function load(silencioso = false) {
  const btnRefresh = document.getElementById("refresh");
  const navDropdown = document.querySelector(".nav-dropdown");

  if (carregando) {
    if (!silencioso) btnRefresh.classList.add("girando");
    return;
  }

  carregando = true;
  let tempoInicio = 0;
  let backendFalhou = false; 
  const grid = document.getElementById("grid");
  
  if (!silencioso) {
    btnRefresh.classList.add("girando");
    tempoInicio = Date.now(); 
    
    if (listaCompleta.length === 0) {
      btnRefresh.classList.add("invisible"); 
      navDropdown.classList.add("invisible"); 
      
      grid.innerHTML = `
        <div class="status-container">
          <div class="loader-spinner"></div>
          <p>${translations[currentLang].searching}</p>
        </div>`;
    }
  }
  
  try {
    const list = await window.api.getPeripherals();
    listaCompleta = list.filter(p => p.name && p.name !== "Periférico Genérico");
    renderizar();
  } catch (e) {
    console.error(e);
    backendFalhou = true; 
    if (!silencioso) {
      // 👇 1. Esconde os botões do topo quando der erro
      btnRefresh.classList.add("invisible");
      navDropdown.classList.add("invisible");
      
      grid.innerHTML = `
        <div class="status-container error-state">
          <span class="error-icon">&#xE783;</span> 
          <h2>${translations[currentLang].error_backend}</h2>
          <p>${translations[currentLang].error_desc}</p>
          <button id="btn-retry" class="retry-btn">${translations[currentLang].btn_retry}</button>
        </div>`;
      
      document.getElementById("btn-retry")?.addEventListener("click", () => {
        listaCompleta = []; 
        
        // 👇 2. Força a tela de pesquisa a aparecer IMEDIATAMENTE ao clicar
        const grid = document.getElementById("grid");
        grid.innerHTML = `
          <div class="status-container">
            <div class="loader-spinner"></div>
            <p>${translations[currentLang].searching}</p>
          </div>`;
          
        load();
      });
    }
  } finally {
    carregando = false;
    
    if (!silencioso) {
      const tempoDecorrido = Date.now() - tempoInicio;
      const tempoRestante = 1000 - (tempoDecorrido % 1000); 
      setTimeout(() => btnRefresh.classList.remove("girando"), tempoRestante);
    } else {
      btnRefresh.classList.remove("girando");
    }
    
    // 👇 3. Só traz o botão de atualizar e o CONECTADOS de volta se NÃO deu erro
    if (!backendFalhou) {
      btnRefresh.classList.remove("invisible"); 
      navDropdown.classList.remove("invisible");
    }
    
    if (!appReadyEnviado) {
      appReadyEnviado = true;
      if (window.api && window.api.appReady) window.api.appReady();
    }
  }
}

// 👇 CORREÇÃO 2: Atualização inteligente (DOM Diffing) para não quebrar o hover
function renderizar() {
  const grid = document.getElementById("grid");
  
  // 👇 A MÁGICA: Remove QUALQUER mensagem de status (Buscando, Vazio, Erro)
  grid.querySelectorAll('.status-msg, .status-container').forEach(el => el.remove());

  const itensParaMostrar = currentView === "connected" 
    ? listaCompleta.filter(p => p.connected)
    : listaCompleta.filter(p => !p.connected);

  // Se não houver itens para mostrar, exibe a mensagem de vazio
  if (itensParaMostrar.length === 0) {
    const msg = currentView === "connected" ? translations[currentLang].empty_connected : translations[currentLang].empty_off;
    grid.innerHTML = `<p class="status-msg empty-msg">${msg}</p>`;
    return;
  }

  // Cria uma lista com os IDs que devem estar na tela
  const idsEsperados = itensParaMostrar.map(p => `card-${(p.master_id || p.name || "desconhecido").replace(/[^a-zA-Z0-9]/g, "_")}`);

  // 1. Remove os cartões que não existem mais
  Array.from(grid.children).forEach(child => {
    if (child.id && child.id.startsWith('card-') && !idsEsperados.includes(child.id)) {
      child.remove();
    }
  });

  // 2. Atualiza os que já existem e cria os novos
  itensParaMostrar.forEach((p, index) => {
    const safeId = `card-${(p.master_id || p.name || "desconhecido").replace(/[^a-zA-Z0-9]/g, "_")}`;
    const novoHtmlString = renderCard(p);
    
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = novoHtmlString.trim();
    const novoElemento = tempDiv.firstElementChild;

    const cardExistente = document.getElementById(safeId);

    if (cardExistente) {
      // Se o cartão já existe, atualiza apenas o conteúdo interno (preserva o hover)
      if (cardExistente.innerHTML !== novoElemento.innerHTML) {
        cardExistente.innerHTML = novoElemento.innerHTML;
      }
      if (cardExistente.className !== novoElemento.className) {
        cardExistente.className = novoElemento.className;
      }
      
      const childAtIndex = grid.children[index];
      if (childAtIndex !== cardExistente) {
        grid.insertBefore(cardExistente, childAtIndex || null);
      }
    } else {
      // Se é um cartão novo, insere na posição correta
      const childAtIndex = grid.children[index] || null;
      grid.insertBefore(novoElemento, childAtIndex);
    }
  });
}

document.getElementById("language-select").addEventListener("change", (e) => {
  localStorage.setItem("lang", e.target.value);
  window.location.reload(); 
});

document.getElementById("theme-select").addEventListener("change", (e) => {
  const newTheme = e.target.value;
  localStorage.setItem("theme", newTheme);
  applyTheme(newTheme);
});

const settingsBtn = document.getElementById("btn-settings");
const settingsMenu = document.getElementById("settings-menu");
settingsBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  settingsMenu.classList.toggle("hidden");
});
document.addEventListener("click", (e) => {
  if (!settingsMenu.contains(e.target) && !settingsBtn.contains(e.target)) {
    settingsMenu.classList.add("hidden");
  }
});

const navCurrent = document.getElementById("nav-text-current");
const navOther = document.getElementById("nav-text-other");

navOther.addEventListener("click", () => {
  if (currentView === "connected") {
    currentView = "off";
    navCurrent.textContent = translations[currentLang].nav_off;
    navCurrent.setAttribute("data-i18n", "nav_off");
    navOther.textContent = translations[currentLang].nav_connected;
    navOther.setAttribute("data-i18n", "nav_connected");
  } else {
    currentView = "connected";
    navCurrent.textContent = translations[currentLang].nav_connected;
    navCurrent.setAttribute("data-i18n", "nav_connected");
    navOther.textContent = translations[currentLang].nav_off;
    navOther.setAttribute("data-i18n", "nav_off");
  }
  
  renderizar(); 
});

document.getElementById("refresh").addEventListener("click", () => load());

applyTheme(localStorage.getItem("theme") || "dark");
applyLanguage();
load();

// ==========================================
// CONTROLES DA JANELA (Unificados e sem duplicação)
// ==========================================
document.getElementById("btn-minimize").addEventListener("click", () => window.api.minimize());
// 👇 O NOVO CLIQUE DO MAXIMIZAR (Com Fade Suave) 👇
document.getElementById("btn-maximize").addEventListener("click", () => {
  // 1. Esmaece a tela (fade-out)
  document.body.classList.add("window-transitioning");
  
  // 2. Espera 150ms (tempo da transição do CSS) e muda o tamanho da janela
  setTimeout(() => {
    window.api.maximize();
    
    // 3. Espera mais 50ms e traz a tela de volta (fade-in)
    setTimeout(() => {
      document.body.classList.remove("window-transitioning");
    }, 50);
  }, 150);
});
document.getElementById("btn-close").addEventListener("click", () => window.api.close());

// 👇 TROCA O ÍCONE BASEADO NO TAMANHO DA JANELA
function atualizarIconeMaximizar() {
  const maxIcon = document.getElementById("maximize-icon");
  if (!maxIcon) return;

  const isMaximized = (window.innerWidth >= screen.availWidth - 10) && (window.innerHeight >= screen.availHeight - 10);

  if (isMaximized) {
    maxIcon.innerHTML = "&#xE923;"; // Restaurar
    document.body.classList.add("is-maximized"); // 👈 Adicione esta linha
  } else {
    maxIcon.innerHTML = "&#xE922;"; // Maximizar
    document.body.classList.remove("is-maximized"); // 👈 Adicione esta linha
  }
}

window.addEventListener('resize', atualizarIconeMaximizar);
atualizarIconeMaximizar();

// Loop de atualização
setInterval(() => { 
  if (!document.hidden) load(true); 
}, 5000);