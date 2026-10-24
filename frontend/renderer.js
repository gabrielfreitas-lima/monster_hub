/**
 * renderer.js
 */

const translations = {
  pt: {
    nav_connected: "CONECTADOS", nav_off: "OFF",
    settings_title: "Configurações", language_label: "Idioma", theme_label: "Tema",
    theme_dark: "🌙 Escuro", theme_light: "☁️ Claro (Cinza)", theme_cream: "🍦 Creme e Roxo",
    searching: "Buscando periféricos...", empty_connected: "Nenhum periférico conectado.",
    empty_off: "Nenhum periférico desconectado.", error_backend: "Erro: Verifique se o backend está rodando!",
    cable: "Cabo", no_battery: "Sem bateria", last_seen: "Última conexão:", new_badge: "NOVO"
  },
  en: {
    nav_connected: "CONNECTED", nav_off: "OFF",
    settings_title: "Settings", language_label: "Language", theme_label: "Theme",
    theme_dark: "🌙 Dark", theme_light: "☁️ Light (Gray)", theme_cream: "🍦 Cream & Purple",
    searching: "Searching for peripherals...", empty_connected: "No peripherals connected.",
    empty_off: "No peripherals disconnected.", error_backend: "Error: Check if the backend is running!",
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

function applyLanguage() {
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.getAttribute("data-i18n");
    if (translations[currentLang][key]) el.textContent = translations[currentLang][key];
  });
  document.getElementById("language-select").value = currentLang;
}

function applyTheme(theme) {
  document.body.classList.remove("light-mode", "cream-purple-mode");
  if (theme === "light") document.body.classList.add("light-mode");
  if (theme === "cream") document.body.classList.add("cream-purple-mode");
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
  
  // Caixas de Som FIXAS: Alexa, Echo, Soundbar (NÃO fones JBL)
  const palavrasCaixaFixa = ["echo", "alexa", "speaker", "soundbar", "homepod", "boombox"];
  const isCaixaDeSomFixa = palavrasCaixaFixa.some(w => nomeLower.includes(w));

  // REGRA DE OURO PARA O JBL: Nunca esconder a bateria de um JBL
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

  return `
    <div class="card ${statusClass} ${memoriaClass}">
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
  if (carregando) return;
  carregando = true;

  const grid = document.getElementById("grid");
  const btnRefresh = document.getElementById("refresh");
  
  if (!silencioso) {
    btnRefresh.classList.add("girando");
    if (listaCompleta.length === 0) {
      grid.innerHTML = `<p style="color:var(--text-muted)">${translations[currentLang].searching}</p>`;
    }
  }
  
  try {
    const list = await window.api.getPeripherals();
    listaCompleta = list.filter(p => p.name && p.name !== "Periférico Genérico");
    renderizar();
  } catch (e) {
    console.error(e);
    if (!silencioso) {
      grid.innerHTML = `<p style="color:#e74c3c">${translations[currentLang].error_backend}</p>`;
    }
  } finally {
    carregando = false;
    btnRefresh.classList.remove("girando");
    if (window.api && window.api.appReady) window.api.appReady();
  }
}

function renderizar() {
  const grid = document.getElementById("grid");
  
  const itensParaMostrar = currentView === "connected" 
    ? listaCompleta.filter(p => p.connected)
    : listaCompleta.filter(p => !p.connected);

  if (itensParaMostrar.length > 0) {
    grid.innerHTML = itensParaMostrar.map(renderCard).join("");
  } else {
    const msg = currentView === "connected" ? translations[currentLang].empty_connected : translations[currentLang].empty_off;
    grid.innerHTML = `<p class="empty-msg">${msg}</p>`;
  }
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

document.getElementById("btn-minimize").addEventListener("click", () => window.api.minimize());
document.getElementById("btn-maximize").addEventListener("click", () => window.api.maximize());
document.getElementById("btn-close").addEventListener("click", () => window.api.close());

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

setInterval(() => { 
  if (!document.hidden) load(true); 
}, 5000);