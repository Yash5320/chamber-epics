import time
from caproto.sync.client import read, write

TEMP_LIMIT = 40.0
VACUUM_LIMIT = 1.0e-5

def trigger_trip(reason):
    print(f'SAFETY INTERLOCK TRIPPED: {reason}')
    write('HEATER:ENABLE', 0)
    write('INTERLOCK:STATUS', f'TRIP: {reason}')

while True:
    temp = read('CAVITY:TEMP').data[0]
    vac = read('CAVITY:VACUUM').data[0]
    status = bytes(read('INTERLOCK:STATUS').data).decode('utf-8').strip('\x00 ')
    if status == 'OK':
        if temp > TEMP_LIMIT:
            trigger_trip(f'Temperature over the limit ({temp:.1f}C)')
        elif vac > VACUUM_LIMIT:
            trigger_trip(f'Vacuum degraded ({vac:.1e})')
    time.sleep(0.1)