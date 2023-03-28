# xiansnn : derived from https://github.com/peterhinch/micropython-samples/ntptime/

# Adapted from official ntptime by Peter Hinch July 2022
# The main aim is portability:
# Detects host device's epoch and returns time relative to that.
# Basic approach to local time: add offset in hours relative to UTC.
# Timeouts return a time of 0. These happen: caller should check for this.
# Replace socket timeout with select.poll as per docs:
# http://docs.micropython.org/en/latest/library/socket.html#socket.socket.settimeout

import socket
import struct
import select
from utime import gmtime
from machine import RTC

HOST_DOMAIN = const("fr.pool.ntp.org")
CLIENT_MODE = const(3)
SERVER_MODE = const(4)
SNTP_VERSION = const(4)
CLOCK_OUT_OF_SYNC = const(3)
DGRAM_SIZE = const(48)
SERVER_REPLY_TIMOUT = const(1) # in seconds

# (date(2000, 1, 1) - date(1900, 1, 1)).days * 24*60*60
# (date(1970, 1, 1) - date(1900, 1, 1)).days * 24*60*60
TIME_STAMP_UNIX = const(2208988800) # first day for UNIX epoch 1970-01-01 00:00
TIME_STAMP_2000 = const(3155673600)
NTP_DELTA = TIME_STAMP_2000 if gmtime(0)[0] == 2000 else TIME_STAMP_UNIX




def get_ntp_time(hrs_offset=0):  # Local time offset in hrs relative to UTC
    NTP_QUERY = bytearray(DGRAM_SIZE)
    NTP_QUERY[0] = (SNTP_VERSION << 3 ) | CLIENT_MODE
    try:
        addr = socket.getaddrinfo(HOST_DOMAIN, 123)[0][-1]
        ntp_server = NTPserver(HOST_DOMAIN)
        ntp_server.ip_address , ntp_server.ip_port = addr
    except OSError:
        return 0
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    poller = select.poll()
    poller.register(s, select.POLLIN)
    try:
        s.sendto(NTP_QUERY, addr)
        if poller.poll(1000):  # time in milliseconds
            msg = s.recv(48)
            frame = NTPframe(msg)
            val = struct.unpack("!I", msg[40:44])[0]  # Can return 0
            return (max(val - NTP_DELTA + hrs_offset * 3600, 0),frame, ntp_server)
    except OSError:
        pass  # LAN error
    finally:
        s.close()
    return 0  # Timeout or LAN error occurred


# There's currently no timezone support in MicroPython, and the RTC is set in UTC time.
def settime(t):
    tm = gmtime(t)
    RTC().datetime((tm[0], tm[1], tm[2], tm[6], tm[3], tm[4], tm[5], 0))
    
def convert_ts_to_time(bin_ts):
    ts = struct.unpack("!II",bin_ts)
    time_ts = gmtime(ts[0] - TIME_STAMP_UNIX)
    return time_ts

def convert_ticks_to_ts(us_ticks):
    sec,usec = divmod(us_ticks,10**6)
    psec = int(usec * (2**32)*(10**-6))
    bin_time = struct.pack("!II",sec,psec)
    return bin_time

def convert_ts_to_ticks(bin_ts):
    sec,psec = struct.unpack("!II",bin_ts)
    us_ticks = (sec + psec*(2**-32))
    return us_ticks

def repr_gmtime(tm):
    return f"{tm[0]:4d}-{tm[1]:02d}-{tm[2]:02d} {tm[3]:02d}:{tm[4]:02d}:{tm[5]:02d} wday:{tm[6]} yday:{tm[7]:03d}"
def repr_RTCdatetime(rtc):
    return f"{rtc[0]:4d}-{rtc[1]:02d}-{rtc[2]:02d} {rtc[4]:02d}:{rtc[5]:02d}:{rtc[6]:02d} wday:{rtc[3]} subsec:{rtc[7]}"


class NTPserver():
    def __init__(self, host="fr.pool.ntp.org"):
        self.host = host
        self.ip_address = ""
        self.ip_port = 0
    def __repr__(self):
        s = "NTP server:"
        s += (f"\n\thost name      {self.host}")
        s += (f"\n\thost ip@:port  {self.ip_address}:{self.ip_port}")
        return s


class NTPframe():
    def __init__(self, msg):
        self.is_valid = True
        self.Leap_Indicator = (msg[0] & 0xC0) >> 6
        self.mode  = msg[0] & 7
        if (self.Leap_Indicator == CLOCK_OUT_OF_SYNC) or (self.mode != SERVER_MODE) :
            self.is_valid = False
        self.version = (msg[0] & 0x38) >> 3
        self.stratum = msg[1]
        poll_exponent = struct.unpack("!b",msg[2:3])[0]
        self.poll_interval = 2** poll_exponent
        precision_exponent = struct.unpack("!b",msg[3:4])[0]
        self.precision = 2**precision_exponent
        self.root_delay = struct.unpack("!hH",msg[4:8])
        self.root_dispersion = struct.unpack("!hH",msg[8:12])
        if self.stratum == 0:
            self.ref_identifier = f"KoD msg:    {msg[12:16].decode('ascii')}"
        elif self.stratum == 1:
            self.ref_identifier = f"source type:    {msg[12:16].decode('ascii')}"
        else:
            ip = list(msg[12:16])
            self.ref_identifier = f"Ref source IP:      {ip[0]}.{ip[1]}.{ip[2]}.{ip[3]}"
        self.ref_time = convert_ts_to_time(msg[16:24])
        self.T1_origine_timestamp = convert_ts_to_ticks(msg[24:32])
        self.T2_receive_timestamp =  convert_ts_to_ticks(msg[32:40])
        self.T3_transmit_timestamp = convert_ts_to_ticks(msg[40:48])
        self.gmt = convert_ts_to_time(msg[40:48])
    
    def __repr__(self):
        s = "NTP frame:\n"
        s += (f"\tLI:{self.Leap_Indicator} | VN:{self.version} | Mode:{self.mode} | Stratum: {self.stratum} | poll_interval: {self.poll_interval} sec | Precision: {self.precision} sec")
        s += (f"\n\tRoot delay:         {self.root_delay[0]}.{self.root_delay[1]} sec")
        s += (f"\n\tRoot dispersion:    {self.root_dispersion[0]}.{self.root_dispersion[1]} sec")
        s += (f"\n\t{self.ref_identifier}")
        s += (f"\n\tRef TimeStamp:      {repr_gmtime(self.ref_time)}")
        s += (f"\n\tTransmit TimeStamp: {repr_gmtime(self.gmt)}")
        return s
                
        
        


###############################################################################
if __name__ == "__main__":
    
    """
    RFC 4330 extract
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


    RTC().datetime()  format :
[0] 'rtc_year'      format yyyy
[1] 'rtc_mon'       range [1 ... 12]
[2] 'rtc_mday'      range [1 ... 31]
[3] 'rtc_wday'      range [0 ... 6] Monday is 0
[4] 'rtc_hour'      range [0 ... 23]
[5] 'rtc_min'       range [0 ... 59]
[6] 'rtc_sec'       range [0 ... 61] 
[7] 'rtc_subsec'    hardware dependant

    time.gmtime()  format :
[0] 'tm_year'      format yyyy
[1] 'tm_mon'       range [1 ... 12]
[2] 'tm_mday'      range [1 ... 31]
[3] 'tm_hour'      range [0 ... 23]
[4] 'tm_min'       range [0 ... 59]
[5] 'tm_sec'       range [0 ... 61] 
[6] 'tm_wday'      range [0 ... 6] Monday is 0
[7] 'tm_yday'      range [1 ... 366]
    
    """
   
    GMT_OFFSET = const(0)  # UTC+0
    CET_OFFSET = const(1)  # UTC+1 Central European Time
    CEST_OFFSET = const(2) # UTC+2 Central European Summer Time
    
    import network
    from lib_pico.wifi_device import WiFiDevice
    if not network.WLAN().isconnected():
        wifi_device = WiFiDevice()
        wifi_device.wifi_connect()
        wifi_device.blocking_wait_connection()
        print(wifi_device)
    ntp_time , frame, server = get_ntp_time(CEST_OFFSET)
    tm = gmtime(ntp_time)
    machine.RTC().datetime((tm[0], tm[1], tm[2], tm[6], tm[3], tm[4], tm[5], 0))
    rtc = machine.RTC().datetime()

    print(server)
    print(frame)
    print(repr_gmtime(tm))
    print(repr_RTCdatetime(rtc))
    
    
    
    