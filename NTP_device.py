import uasyncio as asyncio
from machine import Timer, RTC
import time
import network
import socket
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



def get_ntp_time(era_offset=TIME_STAMP_UNIX, host="fr.pool.ntp.org"):
    NTP_QUERY = bytearray(DATAGRAM_SIZE)
    NTP_QUERY[0] = (SNTP_VERSION << 3 ) | CLIENT_MODE
    addr = socket.getaddrinfo(host, NTP_UDP_PORT)[0][-1]
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.settimeout(1)
        res = s.sendto(NTP_QUERY, addr)
        msg = s.recv(DATAGRAM_SIZE)
#         msg = b'$\x02\x03\xe8\x00\x00\x02\x19\x00\x00\x01\xa9\x11\xfd\x0e\xfd\xe7\xbd\xcck\xe1\x02\x04H\x00\x00\x00\x00\x00\x00\x00\x00\xe7\xbd\xcd\x9a\xf1Y\xc0\xbb\xe7\xbd\xcd\x9a\xf1Z\xf6\x00'
#         msg = b'\x1c\x01\x01\xea\x00\x00\x00\x01\x00\x00\x00\x01GPS\x00\xe7\xbd\xc1\xa8v\xaf\x1co\x00\x00\x00\x00\x00\x00\x00\x00\xe7\xbd\xc1\xb34i\x16\x1c\xe7\xbd\xc1\xb34q\xc5\xa2'
#         print(msg)
        Leap_Indicator = (msg[0] & 0xC0) >> 6
        mode  = msg[0] & 7
        if (Leap_Indicator == CLOCK_OUT_OF_SYNC) or (mode != SERVER_MODE) :
            return None
        Version = (msg[0] & 0x38) >> 3
        stratum = msg[1]
        poll_exponent = unpack("!b",msg[2:3])[0]
        poll_interval = 2** poll_exponent
        precision_exponent = unpack("!b",msg[3:4])[0]
        precision = 2**precision_exponent
        root_delay = unpack("!hH",msg[4:8])
        root_dispersion = unpack("!hH",msg[8:12])
        if stratum == 0:
            ref_identifier = f"KoD msg:{msg[12:16].decode('ascii')}"
        elif stratum == 1:
            ref_identifier = f"source type:{msg[12:16].decode('ascii')}"
        else:
            ip = list(msg[12:16])
            ref_identifier = f"source IP: {ip[0]}.{ip[1]}.{ip[2]}.{ip[3]}"
        ref_timestamp = unpack("!II",msg[16:24])
        origine_timestamp = unpack("!II",msg[24:32])
        receive_timestamp =  unpack("!II",msg[32:40])
        transmit_timestamp = unpack("!II",msg[40:48])
        if __name__ == "__main__":
            print("NTP server host_addr:",addr)
            print("LI:",Leap_Indicator)
            print("VN:",Version)
            print("Mode:",mode)
            print("Stratum:", stratum)
            print(f"poll_interval: {poll_interval} seconds")
            print(f"Precision: {precision} seconds")
            print(f"Root delay: {root_delay[0]}.{root_delay[1]} seconds")
            print(f"Root dispersion: {root_dispersion[0]}.{root_dispersion[1]} seconds",)
            print(ref_identifier)
            print(f"Ref TS: {ref_timestamp[0]}.{ref_timestamp[1]} seconds")
            print(f"Origine TS: {origine_timestamp[0]}.{origine_timestamp[1]} seconds")
            print(f"Receive TS: {receive_timestamp[0]}.{receive_timestamp[1]} seconds")
            print(f"Transmit TS: {transmit_timestamp[0]}.{transmit_timestamp[1]} seconds")
       
    finally:
        pass
#         s.close()
    current_utc_timestamp = transmit_timestamp[0] - era_offset
    return current_utc_timestamp




class NTP_device():
    def __init__(self, time_zone=CET_OFFSET):
        self.time_zone = time_zone
        self.rtc = RTC()
        self.time_validity = wifi_connect()
        current_utc_timestamp = get_ntp_time()
        if current_utc_timestamp is not None:
            local_time = time.localtime(current_utc_timestamp)
        else:
            self.time_validity = False
        # time.localtime = ([0]year, [1]month, [2]mday, [3]hour, [4]minute, [5]second, [6]weekday, [7]yearday)
        # RTC.datetime = ([0]year, [1]month, [2]day, [3]weekday, [4]hours, [5]minutes, [6]seconds, [7]subseconds)
        self.rtc.datetime((local_time[0], local_time[1], local_time[2], local_time[6], local_time[3], local_time[4], local_time[5], 0))
        
    
    def next_second(self):
        pass
#         self.local_time.next_second()            
        
    def get_local_time(self):
        t_RTC = time.localtime()                
        t = list(t_RTC)
        t[3] += self.time_zone
        t[6] += 1
        t[7] = self.time_zone
        t.append(self.time_validity)
        # Format:
        ## localtime : t[0]:year, t[1]:month, t[2]:mday, t[3]:hour, t[4]:minute, t[5]:second, t[6]:weekday, t[7]:time_zone, t[8]=time_validity
        return t
    
    def get_status(self):
        return self.time_validity

if __name__ == "__main__":
    from debug_utility.pulses import *    
    # D0 = Probe(26) # -- time_trigger  
    # D1 = Probe(16) # DCF_Decoder._DCF_clock_IRQ_handler
    # D2 = Probe(17) # DCF_Decoder.frame_decoder
    # D3 = Probe(18) # 
    # D4 = Probe(19) # _StatusController.signal_received
    # D5 = Probe(20) # _StatusController.signal_timeout
    # D6 = Probe(21) # -- time_status == SYNC
    # D7 = Probe(27) #
    
    #--------------------------------------------------------------------------    
    ntp = NTP_device()    
    
    #--------------------------------------------------------------------------    
    def timer_IRQ(timer):
        one_second_time_event.set()

    async def time_trigger():
        while True:
            D0.off()
            await one_second_time_event.wait()
            D0.on()
            one_second_time_event.clear()
            ntp.next_second()
#             print("\t", ntp.get_local_time())
#             print(ntp.get_status())

    Timer(mode=Timer.PERIODIC, freq=1, callback=timer_IRQ)
    one_second_time_event = asyncio.ThreadSafeFlag()
    asyncio.create_task(time_trigger())      
    scheduler = asyncio.get_event_loop()
    scheduler.run_forever()


 