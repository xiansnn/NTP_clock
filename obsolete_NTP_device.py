import uasyncio as asyncio
from machine import Timer, RTC
import time, network, socket
from struct import unpack

from lib_pico.wifi_connect import *


""" RFC 4330 extract
datagram format:
                           1                   2                   3
       0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
      +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
      |LI | VN  |Mode |    Stratum    |     Poll      |   Precision    |
      +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
      |                          Root  Delay                           |
      +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
      |                       Root  Dispersion                         |
      +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
      |                     Reference Identifier                       |
      +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
      |                                                                |
      |                    Reference Timestamp (64)                    |
      |                                                                |
      +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
      |                                                                |
      |                    Originate Timestamp (64)                    |
      |                                                                |
      +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
      |                                                                |
      |                     Receive Timestamp (64)                     |
      |                                                                |
      +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
      |                                                                |
      |                     Transmit Timestamp (64)                    |
      |                                                                |
      +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
      |                 Key Identifier (optional) (32)                 |
      +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
      |                                                                |
      |                                                                |
      |                 Message Digest (optional) (128)                |
      |                                                                |
      |                                                                |
      +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+

LI: Leap Indicator  Meaning
      ---------------------------------------------
      0        no warning
      1        last minute has 61 seconds
      2        last minute has 59 seconds
      3        alarm condition (clock not synchronized)
      
Mode           Meaning
      ------------------------------------
      0        reserved
      1        symmetric active
      2        symmetric passive
      3        client
      4        server
      5        broadcast
      6        reserved for NTP control message
      7        reserved for private use
      
Stratum        Meaning
      ----------------------------------------------
      0        kiss-o'-death message (see below)
      1        primary reference (e.g., synchronized by radio clock)
      2-15     secondary reference (synchronized by NTP or SNTP)
      16-255   reserved
      
Code             External Reference Source
      ------------------------------------------------------------------
      LOCL       uncalibrated local clock
      CESM       calibrated Cesium clock
      RBDM       calibrated Rubidium clock
      PPS        calibrated quartz clock or other pulse-per-second
                 source
      IRIG       Inter-Range Instrumentation Group
      ACTS       NIST telephone modem service
      USNO       USNO telephone modem service
      PTB        PTB (Germany) telephone modem service
      TDF        Allouis (France) Radio 164 kHz
      DCF        Mainflingen (Germany) Radio 77.5 kHz
      MSF        Rugby (UK) Radio 60 kHz
      WWV        Ft. Collins (US) Radio 2.5, 5, 10, 15, 20 MHz
      WWVB       Boulder (US) Radio 60 kHz
      WWVH       Kauai Hawaii (US) Radio 2.5, 5, 10, 15 MHz
      CHU        Ottawa (Canada) Radio 3330, 7335, 14670 kHz
      LORC       LORAN-C radionavigation system
      OMEG       OMEGA radionavigation system
      GPS        Global Positioning Service
"""

CLIENT_MODE = const(3)
SERVER_MODE = const(4)
SNTP_VERSION = const(4)
CLOCK_OUT_OF_SYNC = const(3)
TIME_STAMP_UNIX = const(2208988800) # first day for UNIX epoch 1970-01-01 00:00
CET_OFFSET = 1 # Central European Time
CEST_OFFSET = 2 # Central European Summer Time
DATAGRAM_SIZE = const(48)
NTP_UDP_PORT = const(123)
SERVER_REPLY_TIMOUT = const(1) # in seconds

class NTP_device():
    def __init__(self, time_zone=CET_OFFSET):
        self.time_zone = time_zone
        self.rtc = RTC()
        self._time_validity = False

    def get_time_validity(self):
        return self._time_validity
    
    def set_time_validity(self, bool_value):
        self._time_validity = bool_value

    def get_local_time(self, async_mode=False):
        """ gives time compliant with format expected by clock GUI.
        Unifyed format between ntp, RTC and DCF77"""
        if not self._time_validity:
            if async_mode:
                self._time_validity = async_wifi_connect()
            else:
                self._time_validity = wifi_connect()
            self.set_ntp_time()
        t_RTC = time.gmtime()                
        t = list(t_RTC)
        t[3] += self.time_zone
        t[6] += 1
        t[7] = self.time_zone
        t.append(self._time_validity)
        # t Format:
        ## common_format : t[0]:year, t[1]:month, t[2]:mday, t[3]:hour, t[4]:minute, t[5]:second, t[6]:weekday, t[7]:time_zone, t[8]=time_validity
        return t

    def set_ntp_time(self, era_offset=TIME_STAMP_UNIX, host="fr.pool.ntp.org"):
        NTP_QUERY = bytearray(DATAGRAM_SIZE)
        NTP_QUERY[0] = (SNTP_VERSION << 3 ) | CLIENT_MODE
        self.addr = socket.getaddrinfo(host, NTP_UDP_PORT)[0][-1]
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.settimeout(SERVER_REPLY_TIMOUT)
            res = s.sendto(NTP_QUERY, self.addr)
            msg = s.recv(DATAGRAM_SIZE)
            self.Leap_Indicator = (msg[0] & 0xC0) >> 6
            self.mode  = msg[0] & 7
            if (self.Leap_Indicator == CLOCK_OUT_OF_SYNC) or (self.mode != SERVER_MODE) :
                return None
            self.version = (msg[0] & 0x38) >> 3
            self.stratum = msg[1]
            poll_exponent = unpack("!b",msg[2:3])[0]
            self.poll_interval = 2** poll_exponent
            precision_exponent = unpack("!b",msg[3:4])[0]
            self.precision = 2**precision_exponent
            self.root_delay = unpack("!hH",msg[4:8])
            self.root_dispersion = unpack("!hH",msg[8:12])
            if self.stratum == 0:
                self.ref_identifier = f"KoD msg:{msg[12:16].decode('ascii')}"
            elif self.stratum == 1:
                self.ref_identifier = f"source type:{msg[12:16].decode('ascii')}"
            else:
                ip = list(msg[12:16])
                self.ref_identifier = f"Reference source IP:\n  {ip[0]}.{ip[1]}.{ip[2]}.{ip[3]}"
            self.ref_timestamp = unpack("!II",msg[16:24])
            self.origine_timestamp = unpack("!II",msg[24:32])
            self.receive_timestamp =  unpack("!II",msg[32:40])
            self.transmit_timestamp = unpack("!II",msg[40:48])
            
            current_utc_timestamp = self.transmit_timestamp[0] - era_offset
            gmt = time.gmtime(current_utc_timestamp)
# time.localtime = ([0]year, [1]month, [2]mday, [3]hour,    [4]minute, [5]second,  [6]weekday, [7]yearday)
# RTC.datetime   = ([0]year, [1]month, [2]day,  [3]weekday, [4]hours,  [5]minutes, [6]seconds, [7]subseconds)
            self.rtc.datetime((gmt[0], gmt[1], gmt[2], gmt[6], gmt[3], gmt[4], gmt[5], 0))

            if __name__ == "__main__":
                print(f"NTP server host_addr:{self.addr}")
                print(f"LI: {self.Leap_Indicator}")
                print(f"VN:{self.version}")
                print(f"Mode: {self.mode}")
                print(f"Stratum: {self.stratum}")
                print(f"poll_interval: {self.poll_interval} seconds")
                print(f"Precision: {self.precision} seconds")
                print(f"Root delay: {self.root_delay[0]}.{self.root_delay[1]} seconds")
                print(f"Root dispersion: {self.root_dispersion[0]}.{self.root_dispersion[1]} seconds")
                print(self.ref_identifier)
                print(f"Ref TS: {self.ref_timestamp[0]}.{self.ref_timestamp[1]} seconds")
                print(f"Origine TS: {self.origine_timestamp[0]}.{self.origine_timestamp[1]} seconds")
                print(f"Receive TS: {self.receive_timestamp[0]}.{self.receive_timestamp[1]} seconds")
                print(f"Transmit TS: {self.transmit_timestamp[0]}.{self.transmit_timestamp[1]} seconds")
            
            s.close()
            return True 
        except:
            print("time out reply")
            s.close()
            return False

            
    

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
    ntp = NTP_device()
    
    #--------------------------------------------------------------------------    
    def timer_IRQ(timer):
        one_second_time_event.set()

    async def one_second_time_trigger():
        while True:
            D7.off()
            await one_second_time_event.wait()
            D7.on()
            one_second_time_event.clear()
            print(f"local time: {ntp.get_local_time()}")


    Timer(mode=Timer.PERIODIC, freq=1, callback=timer_IRQ)
    one_second_time_event = asyncio.ThreadSafeFlag()
    asyncio.create_task(one_second_time_trigger())      
    scheduler = asyncio.get_event_loop()
    scheduler.run_forever()


 