import uasyncio as asyncio
from machine import Timer, RTC
import time, network, socket
from struct import unpack

from lib_pico.wifi_device import *
from lib_pico.NTP_client import *



CLIENT_MODE = const(3)
SERVER_MODE = const(4)
SNTP_VERSION = const(4)
CLOCK_OUT_OF_SYNC = const(3)
TIME_STAMP_UNIX = const(2208988800) # first day for UNIX epoch 1970-01-01 00:00
CET_OFFSET = const(1) # Central European Time
CEST_OFFSET = const(2) # Central European Summer Time
DATAGRAM_SIZE = const(48)
NTP_UDP_PORT = const(123)
SERVER_REPLY_TIMOUT = const(1) # in seconds

class NTPdevice():
    def __init__(self, time_zone=CEST_OFFSET):
        self.time_zone = time_zone
        self._time_validity = False

    def time_is_valid(self):
        return self._time_validity
    
    def get_local_time(self):
        """ gives time compliant with format expected by clock GUI.
        Unifyed format between ntp, RTC and DCF77"""
        if not self._time_validity:
            wlan = WiFiDevice()
            wlan.wifi_connect()
            if wlan.blocking_wait_connection():
                self._time_validity = True
                ntp_time,frame,server = get_ntp_time(self.time_zone)
                settime(ntp_time)
        t_RTC = time.gmtime()                
        t = list(t_RTC)
        t[7] = self.time_zone
        t.append(self._time_validity)
        # t Format:
        ## common_format : t[0]:year, t[1]:month, t[2]:mday, t[3]:hour, t[4]:minute, t[5]:second, t[6]:weekday, t[7]:time_zone, t[8]=time_validity
        return t
    
    async def async_get_local_time(self):
        """ gives time compliant with format expected by clock GUI.
        Unifyed format between ntp, RTC and DCF77"""
        if not self._time_validity:
            wlan = WiFiDevice()
            wlan.wifi_connect()
            if wlan.async_wait_connection():
                self._time_validity = True
                ntp_time,frame,server = get_ntp_time(self.time_zone)
                settime(ntp_time)
        t_RTC = time.gmtime()                
        t = list(t_RTC)
        t[7] = self.time_zone
        t.append(self._time_validity)
        # t Format:
        ## common_format : t[0]:year, t[1]:month, t[2]:mday, t[3]:hour, t[4]:minute, t[5]:second, t[6]:weekday, t[7]:time_zone, t[8]=time_validity
        return t
           
    
###############################################################################
if __name__ == "__main__":
    from debug_utility.pulses import *    
    # D0 = Probe(27) # wifi_connect / async_wifi_connect
    # D1 = Probe(16) # wifi_connect>loop / async get_connection_status
    # D2 = Probe(17) # 
    # D3 = Probe(18) # 
    # D4 = Probe(19) # 
    # D5 = Probe(20) # 
    # D6 = Probe(21) # 
    # D7 = Probe(26) # one_second_time_trigger
    
    #--------------------------------------------------------------------------    
    ntp_device = NTPdevice()
    
    #--------------------------------------------------------------------------    
    def timer_IRQ(timer):
        one_second_time_event.set()

    async def one_second_time_trigger():
        while True:
            D7.off()
            await one_second_time_event.wait()
            D7.on()
            one_second_time_event.clear()
            print(f"local time: {ntp_device.get_local_time()}")


    Timer(mode=Timer.PERIODIC, freq=1, callback=timer_IRQ)
    one_second_time_event = asyncio.ThreadSafeFlag()
    asyncio.create_task(one_second_time_trigger())      
    scheduler = asyncio.get_event_loop()
    scheduler.run_forever()


 