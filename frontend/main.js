const { app, BrowserWindow, ipcMain, Menu } = require("electron"); 
const path = require("path");
const { spawn, exec } = require("child_process");
const fs = require("fs");
const koffi = require('koffi');

// Carrega a biblioteca nativa do Windows (DWM)
const dwmapi = koffi.load('dwmapi.dll');
const DwmSetWindowAttribute = dwmapi.func('int __stdcall DwmSetWindowAttribute(void* hwnd, int dwAttribute, void* pvAttribute, int cbAttribute)');

// Constantes do Windows para decoração de janela
const DWMWA_WINDOW_CORNER_PREFERENCE = 33;
const DWMWCP_DONOTROUND = 1; // Não arredondar
const DWMWCP_ROUND = 2;      // Arredondar (padrão do Win11)

const DWMWA_NCRENDERING_POLICY = 2;
const DWMNCRP_DISABLED = 2;  // Desativa a renderização de bordas do sistema
const DWMNCRP_ENABLED = 1;   // Ativa (padrão)

// Função auxiliar para pegar o "Handle" (ID) da janela no Windows
function getHwnd(win) {
  const buffer = win.getNativeWindowHandle();
  return buffer.readBigUInt64LE(0); // Lê o endereço de 64 bits
}

// Função que altera a decoração da janela no Windows
function setWindowsDecorations(win, isMaximized) {
  const hwnd = getHwnd(win);
  
  // Buffers para os valores
  const cornerPref = Buffer.alloc(4);
  const ncPolicy = Buffer.alloc(4);
  const borderColor = Buffer.alloc(4);

  if (isMaximized) {
    // Quando maximizado: remove cantos, desativa renderização da moldura e ZERA a cor da borda
    cornerPref.writeInt32LE(DWMWCP_DONOTROUND);
    ncPolicy.writeInt32LE(DWMNCRP_DISABLED);
    borderColor.writeUInt32LE(0xFFFFFFFE); // 👈 DWMWA_COLOR_NONE
  } else {
    // Quando em janela: restaura cantos, moldura e cor padrão da borda
    cornerPref.writeInt32LE(DWMWCP_ROUND);
    ncPolicy.writeInt32LE(DWMNCRP_ENABLED);
    borderColor.writeUInt32LE(0xFFFFFFFF); // Cor padrão (ou a cor que preferir)
  }

  // Aplica as regras no Windows
  DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, cornerPref, 4);
  DwmSetWindowAttribute(hwnd, DWMWA_NCRENDERING_POLICY, ncPolicy, 4);
  
  // 👇 A NOVA CHAMADA: Remove a linha de 1px
  DwmSetWindowAttribute(hwnd, 34, borderColor, 4); // 34 = DWMWA_BORDER_COLOR
}

// app.disableHardwareAcceleration();
let backendProcess = null;
let mainWindow = null;
let splashWindow = null;

function startBackend() {
  if (app.isPackaged) {
    const backendDir = path.join(process.resourcesPath, "backend");
    const backendPath = path.join(backendDir, "backend.exe");
    
    const logStream = fs.createWriteStream(path.join(app.getPath('userData'), 'backend_log.txt'), { flags: 'a' });
    logStream.write(`\n--- INICIANDO APP ---\nTentando abrir: ${backendPath}\n`);

    // O segredo está no 'cwd': ele diz para o Python rodar de dentro da própria pasta
    backendProcess = spawn(backendPath, [], { 
      windowsHide: true,
      cwd: backendDir // <--- Adicionado aqui
    });
    
    backendProcess.stdout.on("data", (data) => logStream.write(`OUT: ${data}\n`));
    backendProcess.stderr.on("data", (data) => logStream.write(`ERR: ${data}\n`));
    backendProcess.on('error', (err) => {
      logStream.write(`CRASH AO ABRIR: ${err.message}\n`);
    });
  }
}

function createSplash() {
  splashWindow = new BrowserWindow({
    width: 320,
    height: 320,
    frame: false,
    alwaysOnTop: true,
    transparent: true,
    backgroundColor: '#00000000',
    resizable: false,
    show: false,
    webPreferences: { nodeIntegration: false }
  });
  splashWindow.loadFile("splash.html");
  splashWindow.once('ready-to-show', () => splashWindow.show());
}

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1100, 
    height: 700,
    frame: false, 
    show: false, 
    title: "MONSTER HUB",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  mainWindow.loadFile("index.html");
  // Abre o console de desenvolvedor para você ver os erros!
  //mainWindow.webContents.openDevTools(); 
}

function revealApp() {
  if (splashWindow) {
    splashWindow.close();
    splashWindow = null;
  }
  if (mainWindow && !mainWindow.isVisible()) {
    mainWindow.show();
  }
}

ipcMain.handle("fetch-peripherals", async () => {
  const maxRetries = 20; // Tenta por 20 segundos
  const delay = 1000;    

  for (let i = 0; i < maxRetries; i++) {
    try {
      // Removemos o AbortSignal.timeout(2000), agora o fetch espera o tempo que o Python precisar
      const res = await fetch("http://127.0.0.1:8000/peripherals");
      if (res.ok) {
        return await res.json();
      }
    } catch (err) {
      // Se a porta ainda não abriu, ignora e tenta de novo
    }
    await new Promise(r => setTimeout(r, delay));
  }
  throw new Error("Backend não respondeu a tempo.");
});

ipcMain.on("app-ready", () => {
  console.log("O Frontend avisou que está pronto!");
  revealApp();
});

ipcMain.on("window-minimize", () => mainWindow.minimize());
// Variável para guardar o tamanho da janela antes de maximizar
let tamanhoAnterior = { width: 1100, height: 700 };

ipcMain.on("window-maximize", () => {
  const { screen } = require('electron');
  const display = screen.getDisplayMatching(mainWindow.getBounds());
  const workArea = display.workArea; 
  const bounds = mainWindow.getBounds();

  const estaMaximizada = bounds.width >= workArea.width && bounds.height >= workArea.height;

  if (estaMaximizada) {
    // RESTAURAR
    mainWindow.setBounds({ x: 100, y: 100, width: 1100, height: 700 });
    mainWindow.setResizable(true);
    
    // 👇 Avisa o Windows para voltar a arredondar os cantos
    setWindowsDecorations(mainWindow, false);
  } else {
    // MAXIMIZAR
    mainWindow.setBounds({ 
      x: workArea.x, 
      y: workArea.y, 
      width: workArea.width, 
      height: workArea.height 
    });
    mainWindow.setResizable(false);
    
    // 👇 Avisa o Windows para NÃO arredondar e NÃO desenhar borda
    setWindowsDecorations(mainWindow, true);
  }
});

ipcMain.on("window-close", () => mainWindow.close());

app.whenReady().then(() => {
  Menu.setApplicationMenu(null);
  startBackend();
  
  createSplash();
  createMainWindow();

  // TEMPO LIMITE (Força a abertura em 10 segundos)
  setTimeout(() => {
    if (splashWindow) {
      console.log("Tempo esgotado! Forçando abertura da tela principal.");
      revealApp();
    }
  }, 10000);
});

app.on('will-quit', () => {
  if (backendProcess && backendProcess.pid) {
    exec(`taskkill /pid ${backendProcess.pid} /T /F`);
  }
});