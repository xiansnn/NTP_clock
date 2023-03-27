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


CLIENT_MODE = const(3)
SERVER_MODE = const(4)
SNTP_VERSION = const(4)
CLOCK_OUT_OF_SYNC = const(3)
CET_OFFSET = 1 # Central European Time
CEST_OFFSET = 2 # Central European Summer Time
DGRAM_SIZE = const(48)
NTP_UDP_PORT = const(123)
SERVER_REPLY_TIMOUT = const(1) # in seconds

# (date(2000, 1, 1) - date(1900, 1, 1)).days * 24*60*60
# (date(1970, 1, 1) - date(1900, 1, 1)).days * 24*60*60
TIME_STAMP_UNIX = const(2208988800) # first day for UNIX epoch 1970-01-01 00:00
NTP_DELTA = 3155673600 if gmtime(0)[0] == 2000 else TIME_STAMP_UNIX


# The NTP host can be configured at runtime by doing: ntptime.host = 'myhost.org'
host = "fr.pool.ntp.org"

def get_ntp_time(hrs_offset=0):  # Local time offset in hrs relative to UTC
    NTP_QUERY = bytearray(DGRAM_SIZE)
#     NTP_QUERY[0] = 0x1B
    NTP_QUERY[0] = (SNTP_VERSION << 3 ) | CLIENT_MODE
    try:
        addr = socket.getaddrinfo(host, 123)[0][-1]
        print(addr)
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
            return (max(val - NTP_DELTA + hrs_offset * 3600, 0),frame)
    except OSError:
        pass  # LAN error
    finally:
        s.close()
    return 0  # Timeout or LAN error occurred


# There's currently no timezone support in MicroPython, and the RTC is set in UTC time.
def settime(t):
    tm = gmtime(t)
    RTC().datetime((tm[0], tm[1], tm[2], tm[6] + 1, tm[3], tm[4], tm[5], 0))
    
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
        s += (f"\tLI:{self.Leap_Indicator} | VN:{self.version} | Mode:{self.mode} | Stratum:{self.stratum} | poll_interval:{self.poll_interval} sec | Precision:{self.precision} sec")
        s += (f"\n\tRoot delay:         {self.root_delay[0]}.{self.root_delay[1]} sec")
        s += (f"\n\tRoot dispersion:    {self.root_dispersion[0]}.{self.root_dispersion[1]} sec")
        s += (f"\n\t{self.ref_identifier}")
        s += (f"\n\tRef TimeStamp:      {repr_gmtime(self.ref_time)}")
        s += (f"\n\tTransmit TimeStamp: {repr_gmtime(self.gmt)}")
        return s
                
        
        


###############################################################################
if __name__ == "__main__":
    """
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
    from wifi_data import *
    if not network.WLAN().isconnected():
        from wifi_data import *
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        wlan.connect(SSID, PASSWORD)
        print(wlan.ifconfig())
    ntp_time , frame = get_ntp_time(CEST_OFFSET)
    tm = gmtime(ntp_time)
    machine.RTC().datetime((tm[0], tm[1], tm[2], tm[6], tm[3], tm[4], tm[5], 0))
    rtc = machine.RTC().datetime()

    print(frame)    
    print(repr_gmtime(tm))
    print(repr_RTCdatetime(rtc))
    
    
    
    