const { app, BrowserWindow, ipcMain, Menu } = require("electron"); 
const path = require("path");
const { spawn, exec } = require("child_process");
const fs = require("fs");

app.disableHardwareAcceleration();
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
ipcMain.on("window-maximize", () => {
  if (mainWindow.isMaximized()) mainWindow.unmaximize();
  else mainWindow.maximize();
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