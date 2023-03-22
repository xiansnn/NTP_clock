import hardware_setup
from gui.core.ugui import Screen, ssd
from gui.widgets import Label, LED, Dial, Pointer, Button, Textbox
from gui.core.writer import CWriter
# Font for CWriter
import gui.fonts.arial10 as arial10
import gui.fonts.arial35 as hours_font
import gui.fonts.freesans20 as seconds_font
import gui.fonts.freesans20 as date_font
from gui.core.colors import *
#------------------------------------------------------------------------------
# Now import other modules
from cmath import rect, pi
import uasyncio as asyncio
import time

#------------------------------------------------------------------------------
# DEBUG logic analyser probe definitions
from debug_utility.pulses import *
    # D0 = Probe(27) # wifi_connect & async_wifi_connect | DHT11 pulses train
    # D1 = Probe(16) # wifi_connect>loop & async get_connection_status
    # D2 = Probe(17) # 
    # D3 = Probe(18) # NTP_clock_screen.aclock_screen
    # D4 = Probe(19) # 
    # D5 = Probe(20) # 
    # D6 = Probe(21) # 
    # D7 = Probe(26) # one_second_time_trigger


#------------------------------------------------------------------------------
# triggering mechanism = one-second internal timer
from machine import Timer

def one_second_timer_IRQ(timer):
    irq_state = machine.disable_irq()
    asyncio.timer_elapsed.set()
    machine.enable_irq(irq_state)

timer = Timer(mode=Timer.PERIODIC, freq=1, callback=one_second_timer_IRQ)

asyncio.timer_elapsed = asyncio.Event() # evolution possible du Screen : prendre en compte ThreadSafeFlag

# define coroutine that executes each second
async def one_second_coroutine():
    while True:
        D7.off()
        await asyncio.timer_elapsed.wait()
        D7.on()
        asyncio.timer_elapsed.clear()
#         dcf_clock.next_second()

asyncio.create_task(one_second_coroutine())

#------------------------------------------------------------------------------
# import ntp modules
from NTP_clock.NTP_device import *
CET = const(1)
ntp_device = NTP_device(time_zone=CET)

#------------------------------------------------------------------------------
# import and setup temperature and humidity device
from lib_pico.dht_v2 import DHT11device
DHT_PIN_IN = const(9)
PERIOD = const(60)
# active_clock = None
dht11_device = DHT11device(DHT_PIN_IN, PERIOD)
asyncio.create_task(dht11_device.async_measure())

#-------------------------- DCF77 GUI --------------------------------------
# conversions table for Calendar
days   = ('LUN', 'MAR', 'MER', 'JEU', 'VEN', 'SAM', 'DIM')
months = ('JAN', 'FEV', 'MAR', 'AVR', 'MAY', 'JUN', 'JUL', 'AOU', 'SEP', 'OCT', 'NOV', 'DEC')

def fwdbutton(wri, row, col, cls_screen, text='Next'):
    def fwd(button):
        Screen.change(cls_screen)  # Callback
    Button(wri, row, col, callback = fwd,
           height=10, width=20,
           fgcolor = YELLOW, bgcolor = BLACK,
           text = text, shape = RECTANGLE)
    

#------------------------------------------------------------------------------
class NTP_clock_screen(Screen):
    def __init__(self):
        super().__init__()
        labels = {'bdcolor' : False,
                  'fgcolor' : YELLOW,
                  'bgcolor' : BLACK,
                  'justify' : Label.CENTRE,
          }
        temp_colors = {'bdcolor' : False,
                  'fgcolor' : WHITE,
                  'bgcolor' : BLACK,
                  'justify' : Label.CENTRE,
          }
        # verbose default indicates if fast rendering is enabled
        wri         = CWriter(ssd, arial10, YELLOW, BLACK, verbose=False)  
        wri_date    = CWriter(ssd, date_font, YELLOW, BLACK, verbose=False)  
        wri_time    = CWriter(ssd, hours_font, YELLOW, BLACK, verbose=False)  
        wri_seconds = CWriter(ssd, seconds_font, YELLOW, BLACK, verbose=False)  
        wri_temp    = CWriter(ssd, seconds_font, YELLOW, BLACK, verbose=False)  
        
        gap = 4  # Vertical gap between widgets
        
        self.lbl_title = Label(wri, 4, 2, 'NTP clock')

        fwdbutton(wri, 4, 70, NTP_data_screen, text='ntp data')
       
        self.dial = Dial(wri, 20, 2, height = 35, ticks = 12, fgcolor = GREEN, pip = GREEN)
        
        col1 = 2 + self.dial.mcol + 3*gap
        self.lbl_temperature = Label(wri_temp, 20, col1, 40, **temp_colors)
        col2 = self.lbl_temperature.mcol
        self.lbl_temp_unit = Label(wri, 20, col2, "c", **temp_colors)
        row = self.lbl_temperature.mrow
        self.lbl_humidity = Label(wri_temp, row, col1, 40, **temp_colors)
        self.lbl_hum_unit = Label(wri, row, col2, "%", **temp_colors)
        
        row = self.dial.mrow + gap
        self.lbl_date = Label(wri_date, row, 2, 124, **labels)
        row = self.lbl_date.mrow + gap
        self.lbl_tim = Label(wri_time, row, 2, '00:00', **labels)
        self.led_status = LED(wri, row-gap, 105, height=10, bdcolor=False , fgcolor=False )
        row += 12
        self.lbl_sec = Label(wri_seconds, row, 100, '00', **labels)
        
        dht11_device.set_clock( ntp_device)

        # setup async coroutines
        self.reg_task(self.aclock_screen())

    async def aclock_screen(self):
        def uv(phi):
            return rect(1, phi)
        hrs = Pointer(self.dial)
        mins = Pointer(self.dial)
        secs = Pointer(self.dial)

        hstart = 0 + 0.7j  # Pointer lengths. Will rotate relative to top.
        mstart = 0 + 1j
        sstart = 0 + 1j
    
        while True:
            temperature  = dht11_device.get_temperature()
            humidity = dht11_device.get_humidity()
            self.lbl_temperature.value(f"{temperature:3.1f}")
            self.lbl_humidity.value(f"{humidity:3.1f}")
            t = ntp_device.get_local_time()                        
            # Format
            ## localtime : t[0]:year, t[1]:month, t[2]:mday, t[3]:hour, t[4]:minute, t[5]:second, t[6]:weekday, t[7]:time_zone, t[8]:time_is_valid
            hrs.value(hstart * uv(-t[3] * pi/6 - t[4] * pi / 360), CYAN)
            mins.value(mstart * uv(-t[4] * pi/30), CYAN)
            secs.value(sstart * uv(-t[5] * pi/30), RED)
            self.lbl_tim.value(f"{t[3]:02d}:{t[4]:02d}")
            self.lbl_sec.value(f"{t[5]:02d}")
            self.lbl_date.value(f"{days[t[6]-1]} {t[2]} {months[t[1]-1]}")

            self.led_status.color(CYAN)
            if t[5]%2==0 : self.led_status(True)
            else: self.led_status(False)
            D3.off()
            await asyncio.timer_elapsed.wait()
            D3.on()
            asyncio.timer_elapsed.clear()            
            
#------------------------------------------------------------------------------
class NTP_data_screen(Screen):
    def __init__(self):
        super().__init__()
        labels = {'bdcolor' : False,
                  'fgcolor' : YELLOW,
                  'bgcolor' : DARKBLUE,
                  'justify' : Label.CENTRE,
          }

        wri = CWriter(ssd, arial10, YELLOW, BLACK, verbose=False)  # Report on fast mode. Or use verbose=False
        wri_time = CWriter(ssd, seconds_font, YELLOW, BLACK, verbose=False)  # Report on fast mode. Or use verbose=False
        gap = 4  # Vertical gap between widgets

        self.lbl_title = Label(wri, 4, 2, 'data')

        fwdbutton(wri, 4, 45, NTP_clock_screen, text='clock')
        fwdbutton(wri, 4, 85, NTP_init_screen, text='wifi')
        
        row = 22
        self.lbl_date = Label(wri, row, 2, 120, **labels)
        row = self.lbl_date.mrow + gap
        self.tb = Textbox(wri, row, 2, 120, 7)
        self.tb.append(f"NTP server:\n  {ntp_device.addr[0]} : {ntp_device.addr[1]}")
        self.tb.append(f"Stratum: {ntp_device.stratum}")
        self.tb.append(f"poll_interval: {ntp_device.poll_interval} seconds")
        self.tb.append(f"Precision: {ntp_device.precision} seconds")
        self.tb.append(ntp_device.ref_identifier)

        self.reg_task(self.adetail_screen())
       
    async def adetail_screen(self):
        while True:
            t = ntp_device.get_local_time()
            # localtime : t[0]:year, t[1]:month, t[2]:mday, t[3]:hour, t[4]:minute, t[5]:second, t[6]:weekday, t[7]:time_zone
            self.lbl_date.value(f"{days[t[6]-1]} {t[2]:02d} {months[t[1]-1]} {t[3]:02d}:{t[4]:02d}:{t[5]:02d}")

            await asyncio.timer_elapsed.wait()
            asyncio.timer_elapsed.clear()


#------------------------------------------------------------------------------
RETRY_WLAN_CONNECT_STATUS = const(1) # in seconds

class NTP_init_screen(Screen):
    def __init__(self):
        super().__init__()
        labels = {'bdcolor' : False,
                  'fgcolor' : YELLOW,
                  'bgcolor' : DARKBLUE,
                  'justify' : Label.CENTRE,
          }

        wri = CWriter(ssd, arial10, YELLOW, BLACK, verbose=False)  # Report on fast mode. Or use verbose=False
        wri_time = CWriter(ssd, seconds_font, YELLOW, BLACK, verbose=False)  # Report on fast mode. Or use verbose=False
        gap = 4  # Vertical gap between widgets

        self.lbl_title = Label(wri, 4, 2, 'NTP init')

        fwdbutton(wri, 4, 45, NTP_clock_screen, text='clock')
        fwdbutton(wri, 4, 85, NTP_data_screen, text='data')
        
        row = 22
        self.lbl_date = Label(wri, row, 2, 120, **labels)
        row = self.lbl_date.mrow + gap
        self.tb = Textbox(wri, row, 2, 120, 7)

        self.reg_task(self.as_init_screen())
        
        
    async def as_init_screen(self):   
        # async wifi connect and set time
        if not ntp_device.time_is_valid():
#             async_wifi_connect()
            wlan.disconnect()
            wlan.connect(SSID, PASSWORD)
            for n in range(10):
                D4.on()
#                 status = uasyncio.run(get_connection_status())
                status = wlan.status()
                text = explain_wlan_status(status)
                self.tb.append(text)
                D4.off()
                if status == network.STAT_GOT_IP:
#                     wlan_config = wlan.ifconfig()
#                     self.tb.append( f"my_ip =  {wlan_config[0]}" )
                    ntp_device.set_time_validity(True)
                    if ntp_device.set_ntp_time():
                        t = ntp_device.get_local_time()            
                    break
                await uasyncio.sleep(RETRY_WLAN_CONNECT_STATUS)
            t = ntp_device.get_local_time()
            # localtime : t[0]:year, t[1]:month, t[2]:mday, t[3]:hour, t[4]:minute, t[5]:second, t[6]:weekday, t[7]:time_zone
            self.lbl_date.value(f"{days[t[6]-1]} {t[2]:02d} {months[t[1]-1]} {t[3]:02d}:{t[4]:02d}:{t[5]:02d}")
            await uasyncio.sleep(5)
            Screen.change(NTP_clock_screen)
        
        self.reg_task(self.as_init_periodic_screen())
       
        
    
    
    
    async def as_init_periodic_screen(self):
        wlan_config = wlan.ifconfig()
        self.tb.append( f"SSID  =  {SSID}" )
        self.tb.append( f"my_ip =  {wlan_config[0]}" )
        while True:
            t = ntp_device.get_local_time()
            # localtime : t[0]:year, t[1]:month, t[2]:mday, t[3]:hour, t[4]:minute, t[5]:second, t[6]:weekday, t[7]:time_zone
            self.lbl_date.value(f"{days[t[6]-1]} {t[2]:02d} {months[t[1]-1]} {t[3]:02d}:{t[4]:02d}:{t[5]:02d}")
            await asyncio.timer_elapsed.wait()
            asyncio.timer_elapsed.clear()
    


#----------------- main program --------------------------

if __name__ == "__main__":
    Screen.change(NTP_init_screen)




