import hid
import time

VID = 0x3537

def test_multiple_controllers():
    print("🔍 Buscando todos os GameSir conectados...")
    devices = hid.enumerate(VID, 0)
    
    # Filtra apenas as interfaces de dados (0xfff0)
    target_interfaces = [d for d in devices if d['usage_page'] == 0xfff0]
    
    if not target_interfaces:
        print("Nenhum controle GameSir encontrado.")
        return
        
    print(f"🎮 Encontramos {len(target_interfaces)} controle(s)!\n")
    
    heartbeat = [0x0F, 0xF2, 0x00] + [0x00] * 61
    
    for i, d in enumerate(target_interfaces):
        print(f"--- Testando Controle {i+1} ---")
        
        # CORREÇÃO DO PATH: Pega o ID de instância único (ex: 8&2e5cc6f2&0&0001)
        path_str = d['path'].decode()
        unique_id = path_str.split('#')[-2] if '#' in path_str else path_str[-20:]
        print(f"ID Físico Único: {unique_id}")
        
        h = None
        try:
            h = hid.device()
            h.open_path(d['path'])
            
            # Tenta ler alguns pacotes, pois o primeiro pode vir zerado
            battery_encontrada = None
            for tentativa in range(5):
                h.write(heartbeat)
                data = h.read(64, 300) # 300ms
                
                if data and data[0] == 0x12:
                    battery = data[36]
                    if battery > 0 or tentativa == 4: # Se for 0, tenta de novo (até 5 vezes)
                        battery_encontrada = battery
                        charging = data[35]
                        break
                time.sleep(0.1) # Pequena pausa entre tentativas
            
            if battery_encontrada is not None:
                status_str = "Carregando" if charging > 0 else "Descarregando"
                print(f"✅ 🔋 Bateria: {battery_encontrada}% | {status_str}")
            else:
                print("❌ Não foi possível ler a bateria após várias tentativas.")
                
        except Exception as e:
            print(f"⚠️ Erro: {e}")
        finally:
            if h:
                h.close()
                
        print()
        time.sleep(0.5) # Pausa entre os controles

if __name__ == "__main__":
    test_multiple_controllers()