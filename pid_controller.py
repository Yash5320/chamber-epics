from caproto.sync.client import read, write
import time

SETPOINT = 30.0
Kp, Ki, Kd = 12.0,0.8,2.5
integral = 0.0
last_error = 0.0
last_time = time.time()
k=0
print('Starting PID Temperature Controller...')

while True:
    now = time.time()
    dt = max(now-last_time,0.01)
    temp = read('CAVITY:TEMP').data[0]
    k = (k+1)%10

    if k==9:
        print(temp)
    error = temp-SETPOINT
    integral += error*dt
    derivative = (error-last_error)/dt
    output = (Kp*error) + (Ki*integral) + (Kd*derivative)
    valve_pos = max(0.0, min(100.0,output))
    write('CHILLER:VALVE', valve_pos)
    last_error = error
    last_time = now
    
    time.sleep(0.2)
