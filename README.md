> **important notice** : it seems that micropython interpreter setup automatically the RTC at startup. So the NTP device that implement RFC4330 seems not to be very useful.... may be I'll rewrite it when I port the projects in C++

# NTP_clock  
A WIFI connected NTP clock for RP PicoW.  
All details about this protocol wil be found in [RFC4330](https://www.rfc-editor.org/rfc/rfc4330.txt). 


## NTP_device.py

This code connects to the local wifi router, then connects to a NTP server, according to the guidelines given by [NTP organisation](https://www.ntppool.org/en/).  
The received UDP datagram is decoded and the timestamp is converted into time and date by machine.RTC.datetime() function.

This version is a blocking code. In a next version an asynchronous code using uasyncio module will be worked out.

## NTP_clock.py

This code provides for a full clock display, based on [microGUI](https://github.com/peterhinch/micropython-micro-gui)
