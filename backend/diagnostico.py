import hid

# O VID do dongle MCHOSE é 291D. O do cabo é 0D8C.
# Vamos listar todos para garantir.

print("=" * 70)
print("LISTANDO TODOS OS DISPOSITIVOS HID (Filtro MCHOSE/Dongle/Cabo)")
print("=" * 70)

try:
    for d in hid.enumerate():
        vid = d['vendor_id']
        pid = d['product_id']
        prod = d.get('product_string', '') or ''
        manuf = d.get('manufacturer_string', '') or ''
        
        # Filtra pelo VID do dongle (291D), VID do cabo (0D8C) ou nome
        if vid in [0x291D, 0x0D8C] or "MCHOSE" in prod.upper() or "Headset" in prod:
            print(f"VID: {vid:04X} | PID: {pid:04X}")
            print(f"  Produto: {prod}")
            print(f"  Fabricante: {manuf}")
            print(f"  Path: {d['path'].decode(errors='ignore')}")
            print(f"  Interface: {d['interface_number']} | Usage Page: {d['usage_page']:#06x} | Usage: {d['usage']:#06x}")
            print("-" * 70)
except Exception as e:
    print(f"Erro: {e}")