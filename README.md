# monitorBGW

RTP session statistics monitoring and packet capture collecting tool for Avaya G4xx Branch Gateways.

## Intro

Avaya G4xx Branch Gateways are multifunctional gateways that work in conjunction with Avaya Aura® Communication Manager, support Avaya IP and digital phones, analog devices, provide VoIP DSP resources, and optionally WAN router functionalities.

## Business Problem

Troubleshooting voice quality issues has always been challenging for several reasons. One way system administrators can investigate these problems is by reviewing the QoS statistics for RTP streams that a Branch Gateway can collect and store for a limited period of time. In mid to large enterprises with more than a few Branch Gateways, reviewing RTP statistics on each gateway individually can be very time-consuming. While SNMP could be used to collect this information, it is often not configured end-to-end and may even be blocked by firewalls. In contrast, SSH access to Branch Gateways from the Communication Manager almost always works.

## Solution

This tool aims to address the aforementioned challenges by:

- Discovering all Branch Gateways connected to the Communication Manager
- Collecting configuration, hardware, and operational status information from each discovered gateway
- Collecting RTP session statistics from discovered gateways, sorted by timestamp
- Displaying an RTP session summary that highlights problematic sessions more clearly than the default gateway output
- Presenting detailed RTP session information in a format that is easier to understand than the standard CLI output
- Allowing administrators to start and stop the gateway’s capture service (provided the service is enabled)
- Allowing administrators to trigger the upload of gateway packet captures to an HTTP server
- Optionally running a local HTTP server on port 8080 to receive packet trace uploads
- Displaying RTP analysis summaries as provided by tshark when run on the Communication Manager

## How it works

The tool makes use of the standard ***Python 3.6*** libraries, the ***expect*** package, and ***tshark*** as available on Communication Manager 10.x.

If you intend to run this tool outside of Communication Manager, your system must have the ***expect*** package installed, and optionally ***tshark***.

To run it on Communication Manager:

```
python3 monitorBGW -u <user> -p <passwd>
```

When `user` and `passwd` are the SSH credentials to log into the gateways.


### Options

```
optional arguments:
  -h, --help            show this help message and exit
  -u USER               SSH user of the G4xx Gateway
  -p PASSWD             SSH password of the G4xx Gateway
  -n POLLING_SECS       Polling frequency, default 20s
  -m MAX_POLLING        Max simultaneous polling sessions, default 20
  -t TIMEOUT            Query timeout, default 20s
  -i IP                 IP of gateways to discover, default empty
  -l STORAGE_MAXLEN     max number of RTP stats to store, default 999
  --http-server HTTP_SERVER
                        HTTP server IP, default 0.0.0.0
  --http-port HTTP_PORT
                        HTTP server port, default 8080
  --upload_dir UPLOAD_DIR
                        PCAP Upload directory, default /tmp
  --no-http             Don't run HTTP server, default False
  --nok-rtp-only        Store only NOK RTPs, default False
  --loglevel LOGLEVEL   loglevel, default NOTSET (no logging)
  --logfile LOGFILE     log file, default monitorBGW.log
```


## Demo

![alt text](./src/monitorBGW.gif?raw=true "monitorBGW")


## Disclaimer

The author in no way provides any warranty, express or implied, towards the content of traceAMS which was not developed or endorsed by the vendor of Avaya Media Server. It is the user's responsibility to determine the value and quality of this tool which is intended for testing purposes and for use by person at their own discretion and risk.