import time
from pymodbus.client import ModbusTcpClient

IP = '192.168.1.222'
PORT = 502
START_ADDR = 0
COUNT = 100  # Vamos a escanear los primeros 100 registros

print(f"Conectando a {IP}:{PORT}...")
client = ModbusTcpClient(IP, port=PORT)

if not client.connect():
    print("No se pudo conectar al HMI.")
    exit()

print("Conexion exitosa. Tomando lectura inicial...")
initial_data = []

# Leer bloque inicial
response = client.read_holding_registers(address=START_ADDR, count=COUNT, device_id=1)
if not response.isError():
    initial_data = response.registers
else:
    print("Error leyendo los registros.")
    client.close()
    exit()

print("Lectura inicial completada.")
print("\n>>> AHORA ENCIENDE UNA BOMBA EN EL HMI O ESPERA A QUE CAMBIE UN TIEMPO <<<")
print("Esperando 15 segundos...\n")

time.sleep(15)

print("Tomando segunda lectura para comparar...")
response = client.read_holding_registers(address=START_ADDR, count=COUNT, device_id=1)
if not response.isError():
    new_data = response.registers
    
    cambios_encontrados = False
    for i in range(COUNT):
        if initial_data[i] != new_data[i]:
            print(f"✅ ¡REGISTRO ENCONTRADO! Dirección {START_ADDR + i} cambió de {initial_data[i]} a {new_data[i]}")
            cambios_encontrados = True
            
    if not cambios_encontrados:
        print("Ningun registro cambio en este rango. Podrian estar en un rango mas alto (ej. 4000, 8000).")
else:
    print("Error en la segunda lectura.")

client.close()
