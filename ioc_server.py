from caproto.server import PVGroup, pvproperty, run
import numpy as np

class CavityIOC(PVGroup):
    temp = pvproperty(value=25.0, name='CAVITY:TEMP', read_only=True)
    vacuum = pvproperty(value=float(10**(-7)), name='CAVITY:VACUUM', read_only=True)
    valve = pvproperty(value=0.0, name='CHILLER:VALVE')
    heater_enable = pvproperty(value=1, name='HEATER:ENABLE')
    interlock = pvproperty(value='OK', name='INTERLOCK:STATUS', dtype=str, max_length=20)

    @temp.scan(period=0.2)
    async def temp(self, instance, async_lib):
        current_temp = self.temp.value
        heating = 2.5 if self.heater_enable.value == 1 else 0.0
        cooling = (self.valve.value / 100.0) * (current_temp - 15.0) * 0.15
        ambient_loss = (current_temp - 22.0) * 0.02
        noise = np.random.normal(0, 0.02)
        new_temp = round(current_temp + (heating - cooling - ambient_loss) * 0.2 + noise, 3)

        await instance.write(value=new_temp)

    @vacuum.scan(period=0.5)
    async def vacuum(self, instance, async_lib):
        nominal = 1e-7 + abs(np.random.normal(0, 1e-8))
        await instance.write(value=nominal)

if __name__ == '__main__':
    ioc = CavityIOC(prefix='')
    run(ioc.pvdb)