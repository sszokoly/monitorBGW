#!/usr/bin/env python
# -*- encoding: utf-8 -*-

############################## BEGIN IMPORTS #################################
import os
os.environ["ESCDELAY"] = "25"

from abc import ABC, abstractmethod
import _curses, curses, curses.ascii, curses.panel
import functools
import time
import sys
from asyncio import Queue
from datetime import datetime
from typing import Any, Dict, Iterable, List, Tuple, Optional, Callable

############################## END IMPORTS ###################################

from screens import SCREENS, RTP_SCREEN, Screen, iter_rtpdetailed
from bgw import BGW
from storage import MemoryStorage
from rtpparser import parse_rtpstat
from utils import *
from capture import Capture
from datetime import datetime
from curses_helper import terminal_context
from workspace import MyDisplay, Button, Workspace, Tab, ProgressBar, Confirmation, ObjectPanel, TextPanel, FilterPanel
from async_loop import discovery, schedule_http_server, schedule_queries, GWs, BGWs, RTPs, PCAPs
from filter_parser import filter_parser, filter_validator
############################## BEGIN VARIABLES ###############################

FILTER_GROUPs = {
    "bgw": {
        "current_filter": "",
        "no_filter": False,
        "groups": {
            "ip_filter": set(),
            }
        },
}

FILTER_MENUs = {
    "bgw":
"""                                BGW FILTER
Filter Usage:
    -i <IP>    <IP> address of Branch Gateway(s) separated by | or ,
    -n         no filter, clear current filter
 
Filter examples:
  To discover only gateway 10.10.10.1 and 10.10.10.2
    -i 10.10.10.1|10.10.10.2  OR  -i 10.10.10.1,10.10.10.2
"""}

############################## END VARIABLES #################################

# bgw1 = BGW(**{'bgw_ip': '10.10.48.58', 'proto': 'ptls', 'polling_secs': 10, 'bgw_name': 'AvayaG450A', 'bgw_number': '001', 'polls': 1, 'avg_poll_secs': 10, 'active_session_ids': set(), 'last_seen': datetime(2025, 12, 16, 14, 33, 39), 'last_session_id': '', 'show_announcements_files': '\r\n ID      File               Description    Size (Bytes)      Date\r\n---- ------------------ ------------------ ------------ -------------------\r\n101   moh.wav            announcement file      239798    2022-08-23,8:45:26  \r\n102   emergency.wav      announcement file       26618    2023-03-24,11:36:10 \r\n103   public_announceme  announcement file      201914    2024-10-24,7:37:52  \r\n104   mohtest.wav        announcement file     9648106    2025-07-15,14:50:16 \r\n\r\nNv-Ram:\r\nTotal bytes used             : 10119680  \r\nTotal bytes free             : 12672000  \r\nTotal bytes capacity (fixed) : 22791680', 'show_capture': '\r\n\r\nCapture service is enabled and active\r\nCapture start time 09/12/2025-09:25:13\r\nCapture stop time not-stopped\r\nCurrent buffer size is 1024 KB\r\nBuffer mode is non-cyclic\r\nMaximum number of bytes captured from each frame: 4096\r\nCapture list 501 on all interfaces\r\nCapture IPSec decrypted\r\nNumber of captured frames in file: 604 (out of 145200 total captured frames)\r\nMemory buffer occupancy: 4.62% (including overheads)', 'show_faults': '\r\n\r\nCURRENTLY ACTIVE FAULTS\r\n--------------------------------------------------------------------------\r\n\r\n-- Media Module Faults --\r\n\t+ Insertion failure, mmid = v5, 11/24-07:37:04.00\r\n\r\nCurrent Alarm Indications, ALM LED is off\r\n--------------------------------------------------------------------------\r\nNone', 'show_lldp_config': '\r\n\r\nLldp Configuration \r\n-------------------\r\nApplication status: enable \r\nTx interval: 30 seconds\r\nTx hold multiplier: 4 seconds\r\nTx delay: 2 seconds\r\nReinit delay: 2 seconds', 'show_mg_list': '\r\nSLOT   TYPE         CODE        SUFFIX  HW VINTAGE  FW VINTAGE \r\n----   --------     ----------  ------  ----------  -----------\r\nv1     S8300        ICC         E       1           255\r\nv2     -- Not Installed --\r\nv3     E1T1         MM710       B       16          52\r\nv4     -- Not Installed --\r\nv5     -- Initializing --\r\nv6     Analog       MM714       B       23          94\r\nv7     -- Not Installed --\r\nv8     -- Not Installed --\r\nv10    Mainboard    G450        B       2           42.36.0(A)', 'show_port': '\r\nPort   Name             Status    Vlan Level  Neg     Dup. Spd. Type\r\n------ ---------------- --------- ---- ------ ------- ---- ---- ----------------\r\n10/5   NO NAME          connected 1     0     enable  half 1G   Avaya Inc., G450 Media Gateway 10/100/1000BaseTx Port 10/5\r\n\r\n10/6   NO NAME          no link   1     0     enable  full 1G   Avaya Inc., G450 Media Gateway 10/100/1000BaseTx Port 10/6', 'show_rtp_stat_summary': '', 'show_running_config': '\r\n\r\n! version 42.36.0\r\nConfig info release 42.36.0 time "13:33:51 16 DEC 2025 " serial_number 10IS41452851\r\n !\r\nencrypted-username +ikJzwEP/t+XkAlH3l+zsw== password G6uSyomIZMSDb0NnT4RwvSb4IrSGUtuQ9ypCGFikR4w= access-type fe/kaDE5GWBC9Nfj6bNkgA==\r\n!\r\nencrypted-username mJ6sF5BOZeIUWsyCb3C1bw== password 8tMk4PMmywAU0cVXzSERF/aaj9WF0EAq4dB4c0qOLbU= access-type gf0PKwZMZRJ4zRba06ZC3w==\r\nhostname "AvayaG450A"\r\nset system location "Ontario Lab" \r\nno ip telnet \r\nip tftp-server file-system-size 2288\r\nset port mirror source-port 10/5 mirror-port 10/6 sampling always direction both\r\n!\r\nip capture-list 501\r\n name "udp"\r\n!\r\n ip-rule 1\r\n  ip-protocol udp\r\n exit\r\n ip-rule default\r\n  composite-operation "No-Capture"\r\n exit\r\n!\r\nexit\r\n!\r\nds-mode t1\r\n!\r\ninterface Vlan 1\r\n icc-vlan\r\n server-blade-vlan 5\r\n ip address 10.10.48.58     255.255.255.0  \r\n pmi\r\n exit\r\n!\r\ninterface FastEthernet 10/3\r\n exit\r\n!\r\ninterface FastEthernet 10/4\r\n exit\r\n!\r\ninterface Console\r\n speed 9600\r\n exit\r\n!\r\ninterface USB-Modem\r\n description "Default Modem Setup"\r\n timeout absolute 10\r\n ppp authentication ras\r\n no shutdown\r\n ip address 10.3.248.253    255.255.255.252\r\n exit\r\n!\r\ncapture max-frame-size 4096\r\ncapture buffer-mode non-cyclic\r\ncapture filter-group 501\r\nlogin authentication min-password-length 8\r\n!\r\nlogin authentication lockout 0 attempt 0\r\n! Avaya Login Confirmation Received.\r\nEASGManage enableEASG\r\nproduct-id 8c2ae2eead3e6cca800be892bb6e3411\r\n!\r\nset logging file enable \r\nset logging file condition all Error \r\nset logging file condition BOOT Debug \r\n!\r\nno snmp-server community \r\nencrypted-snmp-server user JSXE8Ccs0N0TnuoQek8jwLmaP391mjHjbt9glvbZ2M0= gAAa6QMAG08/c+A= v3ReadISO v3 auth sha 1FCIRMijXV+77fer97/S9O3FlfqIPrTOC5uTFcklYM8=  priv aes128 yyv5YmpCoEn5xZ24B7MR4Y03gnnqwygOY3eQTGRZZB0= \r\nencrypted-snmp-server user 0Ce9aP8Q25tEoXTe0YGwKmt2qLFQJ+UOpG6SMzseQdg= gAAa6QMAG08/c+A= v3TrapISO v3 auth sha TgX0mUpViHn56rSWounTurOYUdreS7rWWY7KssAnYj4=  priv aes128 p5Rdzsia/+4+Uc7f9oeJOj38gI6qX+2Fy1WDL5PTkh8= \r\nsnmp-server group v3ReadISO v3 priv read iso  \r\nsnmp-server group v3TrapISO v3 priv notify iso  \r\nsnmp-server host 10.10.48.92 traps v3 priv bbysnmpv3trap \r\n!\r\nip default-gateway 10.10.48.254    1 low  \r\n!\r\nset sync interface primary v3\r\nset sync source primary\r\nrtp-stat-service\r\nrtp-stat fault\r\nanalog-test\r\nexit\r\n!\r\nset sla-monitor enable\r\nset sla-server-ip-address 10.10.48.198\r\nudp keepalive 10\r\nset mgc list 10.10.48.240\r\nset mediaserver 10.10.48.240 10.10.48.240 23 telnet\r\nset mediaserver 10.10.48.240 10.10.48.240 5023 sat\r\n!#\r\n!# End of configuration file. Press Enter to continue.', 'show_sla_monitor': '\r\n\r\nSLA Monitor:                  Enabled\r\nRegistered Server IP Address: 192.111.111.111\r\nRegistered Server IP Port:    0\r\nConfigured Server IP Address: 10.10.48.198\r\nConfigured Server IP Port:    50011\r\nCapture Mode:                 None\r\nVersion:                      2.7.0', 'show_system': '\r\nSystem Name             : AvayaG450A\r\nSystem Location         : Ontario Lab\r\nSystem Contact          : \r\nUptime (d,h:m:s)        : 422,06:00:13\r\nCall Controller Time    : 13:33:56 16 DEC 2025 \r\nSerial No               : 13TG01116522\r\nModel                   : G430v3\r\nChassis HW Vintage      : 3\r\nChassis HW Suffix       : A\r\nMainboard HW Vintage    : 2\r\nMainboard HW Suffix     : B\r\nMainboard HW CS         : 2.1.7\r\nMainboard FW Vintage    : 42.36.0\r\nLAN MAC Address         : 00:1b:4f:3f:73:e0\r\nWAN1 MAC Address        : 00:1b:4f:3f:73:e1\r\nWAN2 MAC Address        : 00:1b:4f:3f:73:e2\r\nSERVICES MAC address    : 00:1b:4f:3f:73:e3\r\nMemory #1               : 256MB\r\nMemory #2               : Not present\r\nCompact Flash Memory    : 1GB Compact Flash card is installed\r\nPSU #1                  : AC 400W\r\nPSU #2                  : Not present\r\nMedia Socket #1         : MP160 VoIP DSP Module\r\nMedia Socket #2         : Not present\r\nMedia Socket #3         : Not present\r\nMedia Socket #4         : Not present\r\nFAN Tray                : Present', 'show_temp': '\r\nAmbient\r\n-------\r\nTemperature : -5C (23F)\r\nHigh Warning: 42C (108F)\r\nLow Warning : -5C (23F)', 'show_utilization': '\r\n\r\nMod   CPU      CPU     RAM      RAM\r\n      5sec     60sec   used(%)  Total(Kb)\r\n---   ------   -----  -------  ----------\r\n10    Appl. Disabled    48%     190838 Kb', 'show_voip_dsp': '\r\nDSP #1 PARAMETERS\r\n--------------------------------------------------------------\r\nBoard type     : MP160\r\nHw Vintage     : 0 B\r\nFw Vintage     : 182\r\n\r\nDSP#1 CURRENT STATE\r\n--------------------------------------------------------------\r\nIn Use         : 0 of 160 channels, 0 of 4800 points (0.0% used)\r\nState          : Idle\r\nAdmin State    : Release\r\n\r\nCore# Channels Admin     State\r\n      In Use   State\r\n----- -------- --------- -------\r\n    1  0 of 40   Release Idle\r\n    2  0 of 40   Release Idle\r\n    3  0 of 40   Release Idle\r\n    4  0 of 40   Release Idle\r\n\r\n\r\nDSP #2 Not Present\r\n\r\n\r\nDSP #3 Not Present\r\n\r\n\r\nDSP #4 Not Present', 'queue': Queue(), '_active_session': None, '_announcements': None, '_capture_service': None, '_chassis_hw': None, '_comp_flash': None, '_cpu_util': None, '_dsp': None, '_faults': None, '_fw': None, '_hw': None, '_inuse_dsp': None, '_last_seen_time': None, '_lldp': None, '_location': None, '_mac': None, '_mainboard_hw': None, '_memory': None, '_mm_groupdict': None, '_mm_v1': None, '_mm_v2': None, '_mm_v3': None, '_mm_v4': None, '_mm_v5': None, '_mm_v6': None, '_mm_v7': None, '_mm_v8': None, '_mm_v10': None, '_model': None, '_port1': None, '_port1_status': None, '_port1_neg': None, '_port1_duplex': None, '_port1_speed': None, '_port2': None, '_port2_status': None, '_port2_neg': None, '_port2_duplex': None, '_port2_speed': None, '_port_redu': None, '_psu1': None, '_psu2': None, '_ram_util': None, '_rtp_stat_service': None, '_serial': None, '_slamon_service': None, '_sla_server': None, '_snmp': None, '_snmp_trap': None, '_temp': None, '_total_session': None, '_uptime': None})
# bgw2 = BGW(**{'bgw_ip': '10.10.48.59', 'proto': 'ptls', 'polling_secs': 10, 'bgw_name': 'AvayaG450B', 'bgw_number': '002', 'polls': 1, 'avg_poll_secs': 10, 'active_session_ids': set(), 'last_seen': datetime(2025, 12, 16, 14, 33, 39), 'last_session_id': '', 'show_announcements_files': '\r\n ID      File               Description    Size (Bytes)      Date\r\n---- ------------------ ------------------ ------------ -------------------\r\n101   moh.wav            announcement file      239798    2022-08-23,8:45:26  \r\n102   emergency.wav      announcement file       26618    2023-03-24,11:36:10 \r\n103   public_announceme  announcement file      201914    2024-10-24,7:37:52  \r\n104   mohtest.wav        announcement file     9648106    2025-07-15,14:50:16 \r\n\r\nNv-Ram:\r\nTotal bytes used             : 10119680  \r\nTotal bytes free             : 12672000  \r\nTotal bytes capacity (fixed) : 22791680', 'show_capture': '\r\n\r\nCapture service is enabled and active\r\nCapture start time 09/12/2025-09:25:13\r\nCapture stop time not-stopped\r\nCurrent buffer size is 1024 KB\r\nBuffer mode is non-cyclic\r\nMaximum number of bytes captured from each frame: 4096\r\nCapture list 501 on all interfaces\r\nCapture IPSec decrypted\r\nNumber of captured frames in file: 604 (out of 145200 total captured frames)\r\nMemory buffer occupancy: 4.62% (including overheads)', 'show_faults': '\r\n\r\nCURRENTLY ACTIVE FAULTS\r\n--------------------------------------------------------------------------\r\n\r\n-- Media Module Faults --\r\n\t+ Insertion failure, mmid = v5, 11/24-07:37:04.00\r\n\r\nCurrent Alarm Indications, ALM LED is off\r\n--------------------------------------------------------------------------\r\nNone', 'show_lldp_config': '\r\n\r\nLldp Configuration \r\n-------------------\r\nApplication status: disable \r\nTx interval: 30 seconds\r\nTx hold multiplier: 4 seconds\r\nTx delay: 2 seconds\r\nReinit delay: 2 seconds', 'show_mg_list': '\r\nSLOT   TYPE         CODE        SUFFIX  HW VINTAGE  FW VINTAGE \r\n----   --------     ----------  ------  ----------  -----------\r\nv1     -- Not Installed --\r\nv2     -- Not Installed --\r\nv3     E1T1         MM710       B       16          52\r\nv4     -- Not Installed --\r\nv5     -- Initializing --\r\nv6     Analog       MM714       B       23          94\r\nv7     -- Not Installed --\r\nv8     -- Not Installed --\r\nv10    Mainboard    G450        B       2           42.36.0(A)', 'show_port': '\r\nPort   Name             Status    Vlan Level  Neg     Dup. Spd. Type\r\n------ ---------------- --------- ---- ------ ------- ---- ---- ----------------\r\n10/5   NO NAME          connected 1     0     enable  full 1G   Avaya Inc., G450 Media Gateway 10/100/1000BaseTx Port 10/5\r\n\r\n10/6   NO NAME          connected   1     0     enable  half 10M   Avaya Inc., G450 Media Gateway 10/100/1000BaseTx Port 10/6', 'show_rtp_stat_summary': '', 'show_running_config': '\r\n\r\n! version 42.36.0\r\nConfig info release 42.36.0 time "13:33:51 16 DEC 2025 " serial_number 10IS41452851\r\n !\r\nencrypted-username +ikJzwEP/t+XkAlH3l+zsw== password G6uSyomIZMSDb0NnT4RwvSb4IrSGUtuQ9ypCGFikR4w= access-type fe/kaDE5GWBC9Nfj6bNkgA==\r\n!\r\nencrypted-username mJ6sF5BOZeIUWsyCb3C1bw== password 8tMk4PMmywAU0cVXzSERF/aaj9WF0EAq4dB4c0qOLbU= access-type gf0PKwZMZRJ4zRba06ZC3w==\r\nhostname "AvayaG450A"\r\nset system location "Calgary" \r\nno ip telnet \r\nip tftp-server file-system-size 2288\r\nset port mirror source-port 10/5 mirror-port 10/6 sampling always direction both\r\n!\r\nip capture-list 501\r\n name "udp"\r\n!\r\n ip-rule 1\r\n  ip-protocol udp\r\n exit\r\n ip-rule default\r\n  composite-operation "No-Capture"\r\n exit\r\n!\r\nexit\r\n!\r\nds-mode t1\r\n!\r\ninterface Vlan 1\r\n icc-vlan\r\n server-blade-vlan 5\r\n ip address 10.10.48.59     255.255.255.0  \r\n pmi\r\n exit\r\n!\r\ninterface FastEthernet 10/3\r\n exit\r\n!\r\ninterface FastEthernet 10/4\r\n exit\r\n!\r\ninterface Console\r\n speed 9600\r\n exit\r\n!\r\ninterface USB-Modem\r\n description "Default Modem Setup"\r\n timeout absolute 10\r\n ppp authentication ras\r\n no shutdown\r\n ip address 10.3.248.253    255.255.255.252\r\n exit\r\n!\r\ncapture max-frame-size 4096\r\ncapture buffer-mode non-cyclic\r\ncapture filter-group 501\r\nlogin authentication min-password-length 8\r\n!\r\nlogin authentication lockout 0 attempt 0\r\n! Avaya Login Confirmation Received.\r\nEASGManage enableEASG\r\nproduct-id 8c2ae2eead3e6cca800be892bb6e3411\r\n!\r\nset logging file enable \r\nset logging file condition all Error \r\nset logging file condition BOOT Debug \r\n!\r\nno snmp-server community \r\nencrypted-snmp-server user JSXE8Ccs0N0TnuoQek8jwLmaP391mjHjbt9glvbZ2M0= gAAa6QMAG08/c+A= v3ReadISO v3 auth sha 1FCIRMijXV+77fer97/S9O3FlfqIPrTOC5uTFcklYM8=  priv aes128 yyv5YmpCoEn5xZ24B7MR4Y03gnnqwygOY3eQTGRZZB0= \r\nencrypted-snmp-server user 0Ce9aP8Q25tEoXTe0YGwKmt2qLFQJ+UOpG6SMzseQdg= gAAa6QMAG08/c+A= v3TrapISO v3 auth sha TgX0mUpViHn56rSWounTurOYUdreS7rWWY7KssAnYj4=  priv aes128 p5Rdzsia/+4+Uc7f9oeJOj38gI6qX+2Fy1WDL5PTkh8= \r\nsnmp-server group v3ReadISO v3 priv read iso  \r\nsnmp-server group v3TrapISO v3 priv notify iso  \r\nsnmp-server host 10.10.48.92 traps v3 priv bbysnmpv3trap \r\n!\r\nip default-gateway 10.10.48.254    1 low  \r\n!\r\nset sync interface primary v3\r\nset sync source primary\r\nrtp-stat-service\r\nrtp-stat fault\r\nanalog-test\r\nexit\r\n!\r\nset sla-monitor enable\r\nset sla-server-ip-address 10.10.48.198\r\nudp keepalive 10\r\nset mgc list 10.10.48.240\r\nset mediaserver 10.10.48.240 10.10.48.240 23 telnet\r\nset mediaserver 10.10.48.240 10.10.48.240 5023 sat\r\n!#\r\n!# End of configuration file. Press Enter to continue.', 'show_sla_monitor': '\r\n\r\nSLA Monitor:                  Enabled\r\nRegistered Server IP Address: 0.0.0.0\r\nRegistered Server IP Port:    0\r\nConfigured Server IP Address: 10.10.48.198\r\nConfigured Server IP Port:    50011\r\nCapture Mode:                 None\r\nVersion:                      2.7.0', 'show_system': '\r\nSystem Name             : AvayaG450B\r\nSystem Location         : Calgary\r\nSystem Contact          : \r\nUptime (d,h:m:s)        : 22,06:00:13\r\nCall Controller Time    : 13:33:56 16 DEC 2025 \r\nSerial No               : 13TG01116522\r\nModel                   : G450\r\nChassis HW Vintage      : 1\r\nChassis HW Suffix       : A\r\nMainboard HW Vintage    : 2\r\nMainboard HW Suffix     : B\r\nMainboard HW CS         : 2.1.7\r\nMainboard FW Vintage    : 42.36.0\r\nLAN MAC Address         : 00:1b:4f:3f:73:e8\r\nWAN1 MAC Address        : 00:1b:4f:3f:73:e1\r\nWAN2 MAC Address        : 00:1b:4f:3f:73:e2\r\nSERVICES MAC address    : 00:1b:4f:3f:73:e3\r\nMemory #1               : 256MB\r\nMemory #2               : Not present\r\nCompact Flash Memory    : No CompactFlash card is installed\r\nPSU #1                  : AC 400W\r\nPSU #2                  : AC 400W\r\nMedia Socket #1         : MP160 VoIP DSP Module\r\nMedia Socket #2         : Not present\r\nMedia Socket #3         : Not present\r\nMedia Socket #4         : Not present\r\nFAN Tray                : Present', 'show_temp': '\r\nAmbient\r\n-------\r\nTemperature : 42C (108F)\r\nHigh Warning: 42C (108F)\r\nLow Warning : -5C (23F)', 'show_utilization': '\r\n\r\nMod   CPU      CPU     RAM      RAM\r\n      5sec     60sec   used(%)  Total(Kb)\r\n---   ------   -----  -------  ----------\r\n10    Appl. Disabled    48%     190838 Kb', 'show_voip_dsp': '\r\nDSP #1 PARAMETERS\r\n--------------------------------------------------------------\r\nBoard type     : MP160\r\nHw Vintage     : 0 B\r\nFw Vintage     : 182\r\n\r\nDSP#1 CURRENT STATE\r\n--------------------------------------------------------------\r\nIn Use         : 0 of 160 channels, 0 of 4800 points (0.0% used)\r\nState          : Idle\r\nAdmin State    : Release\r\n\r\nCore# Channels Admin     State\r\n      In Use   State\r\n----- -------- --------- -------\r\n    1  0 of 40   Release Idle\r\n    2  0 of 40   Release Idle\r\n    3  0 of 40   Release Idle\r\n    4  0 of 40   Release Idle\r\n\r\n\r\nDSP #2 Not Present\r\n\r\n\r\nDSP #3 Not Present\r\n\r\n\r\nDSP #4 Not Present', 'queue': Queue(), '_active_session': None, '_announcements': None, '_capture_service': None, '_chassis_hw': None, '_comp_flash': None, '_cpu_util': None, '_dsp': None, '_faults': None, '_fw': None, '_hw': None, '_inuse_dsp': None, '_last_seen_time': None, '_lldp': None, '_location': None, '_mac': None, '_mainboard_hw': None, '_memory': None, '_mm_groupdict': None, '_mm_v1': None, '_mm_v2': None, '_mm_v3': None, '_mm_v4': None, '_mm_v5': None, '_mm_v6': None, '_mm_v7': None, '_mm_v8': None, '_mm_v10': None, '_model': None, '_port1': None, '_port1_status': None, '_port1_neg': None, '_port1_duplex': None, '_port1_speed': None, '_port2': None, '_port2_status': None, '_port2_neg': None, '_port2_duplex': None, '_port2_speed': None, '_port_redu': None, '_psu1': None, '_psu2': None, '_ram_util': None, '_rtp_stat_service': None, '_serial': None, '_slamon_service': None, '_sla_server': None, '_snmp': None, '_snmp_trap': None, '_temp': None, '_total_session': None, '_uptime': None})
# bgw3 = BGW(**{'bgw_ip': '192.168.110.111', 'proto': 'ptls', 'polling_secs': 10, 'bgw_name': 'AvayaG450C', 'bgw_number': '003', 'polls': 1, 'avg_poll_secs': 10, 'active_session_ids': set(), 'last_seen': datetime(2025, 12, 16, 14, 33, 39), 'last_session_id': '', 'show_announcements_files': '\r\n ID      File               Description    Size (Bytes)      Date\r\n---- ------------------ ------------------ ------------ -------------------\r\n101   moh.wav            announcement file      239798    2022-08-23,8:45:26  \r\n102   emergency.wav      announcement file       26618    2023-03-24,11:36:10 \r\n103   public_announceme  announcement file      201914    2024-10-24,7:37:52  \r\n104   mohtest.wav        announcement file     9648106    2025-07-15,14:50:16 \r\n\r\nNv-Ram:\r\nTotal bytes used             : 10119680  \r\nTotal bytes free             : 12672000  \r\nTotal bytes capacity (fixed) : 22791680', 'show_capture': '\r\n\r\nCapture service is enabled and active\r\nCapture start time 09/12/2025-09:25:13\r\nCapture stop time not-stopped\r\nCurrent buffer size is 1024 KB\r\nBuffer mode is non-cyclic\r\nMaximum number of bytes captured from each frame: 4096\r\nCapture list 501 on all interfaces\r\nCapture IPSec decrypted\r\nNumber of captured frames in file: 604 (out of 145200 total captured frames)\r\nMemory buffer occupancy: 4.62% (including overheads)', 'show_faults': '\r\n\r\nNo Fault Messages\r\n--------------------------------------------------------------------------\r\nNone', 'show_lldp_config': '\r\n\r\nLldp Configuration \r\n-------------------\r\nApplication status: disable \r\nTx interval: 30 seconds\r\nTx hold multiplier: 4 seconds\r\nTx delay: 2 seconds\r\nReinit delay: 2 seconds', 'show_mg_list': '\r\nSLOT   TYPE         CODE        SUFFIX  HW VINTAGE  FW VINTAGE \r\n----   --------     ----------  ------  ----------  -----------\r\nv1     -- Not Installed --\r\nv2     -- Not Installed --\r\nv3     E1T1         MM710       B       16          52\r\nv4     -- Not Installed --\r\nv5     -- Initializing --\r\nv6     Analog       MM714       B       23          104\r\nv7     Analog       MM714       A       23          114\r\nv8     -- Not Installed --\r\nv10    Mainboard    G450        B       2           42.36.0(A)', 'show_port': '\r\nPort   Name             Status    Vlan Level  Neg     Dup. Spd. Type\r\n------ ---------------- --------- ---- ------ ------- ---- ---- ----------------\r\n10/5   NO NAME          connected 1     0     enable  full 1G   Avaya Inc., G450 Media Gateway 10/100/1000BaseTx Port 10/5\r\n\r\n10/6   NO NAME          no link   1     0     enable  full 1G   Avaya Inc., G450 Media Gateway 10/100/1000BaseTx Port 10/6', 'show_rtp_stat_summary': '', 'show_running_config': '\r\n\r\n! version 42.36.0\r\nConfig info release 42.36.0 time "13:33:51 16 DEC 2025 " serial_number 10IS41452851\r\n !\r\nencrypted-username +ikJzwEP/t+XkAlH3l+zsw== password G6uSyomIZMSDb0NnT4RwvSb4IrSGUtuQ9ypCGFikR4w= access-type fe/kaDE5GWBC9Nfj6bNkgA==\r\n!\r\nencrypted-username mJ6sF5BOZeIUWsyCb3C1bw== password 8tMk4PMmywAU0cVXzSERF/aaj9WF0EAq4dB4c0qOLbU= access-type gf0PKwZMZRJ4zRba06ZC3w==\r\nhostname "AvayaG450A"\r\nset system location "Calgary" \r\nno ip telnet \r\nip tftp-server file-system-size 2288\r\nset port mirror source-port 10/5 mirror-port 10/6 sampling always direction both\r\n!\r\nip capture-list 501\r\n name "udp"\r\n!\r\n ip-rule 1\r\n  ip-protocol udp\r\n exit\r\n ip-rule default\r\n  composite-operation "No-Capture"\r\n exit\r\n!\r\nexit\r\n!\r\nds-mode t1\r\n!\r\ninterface Vlan 1\r\n icc-vlan\r\n server-blade-vlan 5\r\n ip address 192.168.110.111     255.255.255.0  \r\n pmi\r\n exit\r\n!\r\ninterface FastEthernet 10/3\r\n exit\r\n!\r\ninterface FastEthernet 10/4\r\n exit\r\n!\r\ninterface Console\r\n speed 9600\r\n exit\r\n!\r\ninterface USB-Modem\r\n description "Default Modem Setup"\r\n timeout absolute 10\r\n ppp authentication ras\r\n no shutdown\r\n ip address 10.3.248.253    255.255.255.252\r\n exit\r\n!\r\ncapture max-frame-size 4096\r\ncapture buffer-mode non-cyclic\r\ncapture filter-group 501\r\nlogin authentication min-password-length 8\r\n!\r\nlogin authentication lockout 0 attempt 0\r\n! Avaya Login Confirmation Received.\r\nEASGManage enableEASG\r\nproduct-id 8c2ae2eead3e6cca800be892bb6e3411\r\n!\r\nset logging file enable \r\nset logging file condition all Error \r\nset logging file condition BOOT Debug \r\n!\r\nno snmp-server community \r\nencrypted-snmp-server user JSXE8Ccs0N0TnuoQek8jwLmaP391mjHjbt9glvbZ2M0= gAAa6QMAG08/c+A= v3ReadISO v3 auth sha 1FCIRMijXV+77fer97/S9O3FlfqIPrTOC5uTFcklYM8=  priv aes128 yyv5YmpCoEn5xZ24B7MR4Y03gnnqwygOY3eQTGRZZB0= \r\nencrypted-snmp-server user 0Ce9aP8Q25tEoXTe0YGwKmt2qLFQJ+UOpG6SMzseQdg= gAAa6QMAG08/c+A= v3TrapISO v3 auth sha TgX0mUpViHn56rSWounTurOYUdreS7rWWY7KssAnYj4=  priv aes128 p5Rdzsia/+4+Uc7f9oeJOj38gI6qX+2Fy1WDL5PTkh8= \r\nsnmp-server group v3ReadISO v3 priv read iso  \r\nsnmp-server group v3TrapISO v3 priv notify iso  \r\nsnmp-server host 10.10.48.92 traps v3 priv bbysnmpv3trap \r\n!\r\nip default-gateway 10.10.48.254    1 low  \r\n!\r\nset sync interface primary v3\r\nset sync source primary\r\nrtp-stat-service\r\nrtp-stat fault\r\nanalog-test\r\nexit\r\n!\r\nset sla-monitor enable\r\nset sla-server-ip-address 10.10.48.198\r\nudp keepalive 10\r\nset mgc list 10.10.48.240\r\nset mediaserver 10.10.48.240 10.10.48.240 23 telnet\r\nset mediaserver 10.10.48.240 10.10.48.240 5023 sat\r\n!#\r\n!# End of configuration file. Press Enter to continue.', 'show_sla_monitor': '\r\n\r\nSLA Monitor:                 Disabled\r\nRegistered Server IP Address: 0.0.0.0\r\nRegistered Server IP Port:    0\r\nConfigured Server IP Address: 10.10.48.198\r\nConfigured Server IP Port:    50011\r\nCapture Mode:                 None\r\nVersion:                      2.7.0', 'show_system': '\r\nSystem Name             : AvayaG450C\r\nSystem Location         : Calgary\r\nSystem Contact          : \r\nUptime (d,h:m:s)        : 22,06:00:13\r\nCall Controller Time    : 13:33:56 16 DEC 2025 \r\nSerial No               : 13TG01116522\r\nModel                   : G450\r\nChassis HW Vintage      : 1\r\nChassis HW Suffix       : A\r\nMainboard HW Vintage    : 2\r\nMainboard HW Suffix     : B\r\nMainboard HW CS         : 2.1.7\r\nMainboard FW Vintage    : 42.36.0\r\nLAN MAC Address         : 00:1b:4f:3f:73:e4\r\nWAN1 MAC Address        : 00:1b:4f:3f:73:e1\r\nWAN2 MAC Address        : 00:1b:4f:3f:73:e2\r\nSERVICES MAC address    : 00:1b:4f:3f:73:e4\r\nMemory #1               : 256MB\r\nMemory #2               : Not present\r\nCompact Flash Memory    : No CompactFlash card is installed\r\nPSU #1                  : AC 400W\r\nPSU #2                  : Not present\r\nMedia Socket #1         : MP160 VoIP DSP Module\r\nMedia Socket #2         : Not present\r\nMedia Socket #3         : Not present\r\nMedia Socket #4         : Not present\r\nFAN Tray                : Present', 'show_temp': '\r\nAmbient\r\n-------\r\nTemperature : 36C (97F)\r\nHigh Warning: 42C (108F)\r\nLow Warning : -5C (23F)', 'show_utilization': '\r\n\r\nMod   CPU      CPU     RAM      RAM\r\n      5sec     60sec   used(%)  Total(Kb)\r\n---   ------   -----  -------  ----------\r\n10    Appl. Disabled    48%     190838 Kb', 'show_voip_dsp': '\r\nDSP #1 PARAMETERS\r\n--------------------------------------------------------------\r\nBoard type     : MP160\r\nHw Vintage     : 0 B\r\nFw Vintage     : 182\r\n\r\nDSP#1 CURRENT STATE\r\n--------------------------------------------------------------\r\nIn Use         : 0 of 160 channels, 0 of 4800 points (0.0% used)\r\nState          : Idle\r\nAdmin State    : Release\r\n\r\nCore# Channels Admin     State\r\n      In Use   State\r\n----- -------- --------- -------\r\n    1  0 of 40   Release Idle\r\n    2  0 of 40   Release Idle\r\n    3  0 of 40   Release Idle\r\n    4  0 of 40   Release Idle\r\n\r\n\r\nDSP #2 Not Present\r\n\r\n\r\nDSP #3 Not Present\r\n\r\n\r\nDSP #4 Not Present', 'queue': Queue(), '_active_session': None, '_announcements': None, '_capture_service': None, '_chassis_hw': None, '_comp_flash': None, '_cpu_util': None, '_dsp': None, '_faults': None, '_fw': None, '_hw': None, '_inuse_dsp': None, '_last_seen_time': None, '_lldp': None, '_location': None, '_mac': None, '_mainboard_hw': None, '_memory': None, '_mm_groupdict': None, '_mm_v1': None, '_mm_v2': None, '_mm_v3': None, '_mm_v4': None, '_mm_v5': None, '_mm_v6': None, '_mm_v7': None, '_mm_v8': None, '_mm_v10': None, '_model': None, '_port1': None, '_port1_status': None, '_port1_neg': None, '_port1_duplex': None, '_port1_speed': None, '_port2': None, '_port2_status': None, '_port2_neg': None, '_port2_duplex': None, '_port2_speed': None, '_port_redu': None, '_psu1': None, '_psu2': None, '_ram_util': None, '_rtp_stat_service': None, '_serial': None, '_slamon_service': None, '_sla_server': None, '_snmp': None, '_snmp_trap': None, '_temp': None, '_total_session': None, '_uptime': None})
# BGWs = MemoryStorage({'001': bgw1, '002': bgw2, '003': bgw3})
# GWs = {'10.10.48.58': "001", "10.10.48.59": "002", "192.168.110.111": "003", "10.44.244.51": "004", "10.188.244.1": "005"}

# RTPs = MemoryStorage()
# d = {
#     "2024-11-04,10:06:07,001,00001": "\r\nshow rtp-stat detailed 00001\r\n\r\nSession-ID: 21\r\nStatus: Terminated, QOS: Faulted, EngineId: 10\r\nStart-Time: 2024-11-04,10:06:07, End-Time: 2024-11-04,10:07:07\r\nDuration: 00:02:00\r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.111:2052 SSRC 1653399062\r\nRemote-Address: 10.10.48.192:35000 SSRC 2704961869 (0)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG729A 200B 20mS srtpAesCm128HmacSha180, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 4.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 0.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 1243, Loss 0.3% #0, Avg-Loss 0.3%, RTT 0mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 0, Seq-Fall 1, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 0, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 1.0% #0, Avg-Loss 0.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n",
#     "2025-12-14,10:07:27,002,00002": "\r\nshow rtp-stat detailed 00002\r\n\r\nSession-ID: 11\r\nStatus: Active, QOS: Ok, EngineId: 10\r\nStart-Time: 2025-12-14,10:07:27, End-Time: -\r\nDuration: - \r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.112:2052 SSRC 1653399062\r\nRemote-Address: 10.10.48.192:35000 SSRC 2704961869 (2)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG711U 200B 20mS srtpAesCm128HmacSha180, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 334.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 0.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 123, Loss 0.3% #0, Avg-Loss 0.3%, RTT 200mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 2, Seq-Fall 0, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 46, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 2.0% #0, Avg-Loss 1.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n",
#     "2025-12-14,10:08:07,003,00001": "\r\nshow rtp-stat detailed 00001\r\n\r\nSession-ID: 1\r\nStatus: Active, QOS: Ok, EngineId: 10\r\nStart-Time: 2025-12-14,10:08:07, End-Time: 2025-12-14,10:08:22\r\nDuration: 00:12:20\r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.113:2056 SSRC 1653399062\r\nRemote-Address: 192.168.110.111:35001 SSRC 2704961869 (0)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG711U 230B 30mS Off, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 334.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 1.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 0, Loss 0.3% #0, Avg-Loss 0.3%, RTT 0mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 0, Seq-Fall 0, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 46, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 0.0% #0, Avg-Loss 0.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n",

# }
# for global_id, value in d.items():
#         rtpdetailed = parse_rtpstat(global_id, value)
#         RTPs.put({global_id: rtpdetailed})

# PCAPS = MemoryStorage({
#     '2025_12_19@22_05_45_002':
#     Capture(remote_ip='10.44.244.51', filename='2025_12_19@22_05_45_002', file_size=6539, received_timestamp=datetime(2025, 12, 20, 11, 9, 19, 550802), capinfos='File name:           uploads/2025_12_19@22_05_45_002\nFile type:           Wireshark/tcpdump/... - pcap\nFile encapsulation:  Ethernet\nFile timestamp precision:  microseconds (6)\nPacket size limit:   file hdr: 4096 bytes\nNumber of packets:   4,565\nFile size:           1,048 kB\nData size:           975 kB\nCapture duration:    22.065001 seconds\nFirst packet time:   2025-11-27 08:52:08.265000\nLast packet time:    2025-11-27 08:52:30.330001\nData byte rate:      44 kBps\nData bit rate:       353 kbps\nAverage packet size: 213.69 bytes\nAverage packet rate: 206 packets/s\nSHA256:              41f4feebdc3012525069ee9cf471d93e980779cfb700269dccf9568b7b8cc598\nRIPEMD160:           365e85e95f27a660e8fc616c917b59b1d7e13544\nSHA1:                21a9247795c835ed5c62aaa9cde95bffc2031908\nStrict time order:   False\nNumber of interfaces in file: 1\nInterface #0 info:\n                     Encapsulation = Ethernet (1 - ether)\n                     Capture length = 4096\n                     Time precision = microseconds (6)\n                     Time ticks per second = 1000000\n                     Number of stat entries = 0\n                     Number of packets = 4565', rtpinfos='========================= RTP Streams ========================\n    Src IP addr  Port    Dest IP addr  Port       SSRC          Payload  Pkts         Lost   Max Delta(ms)  Max Jitter(ms) Mean Jitter(ms) Problems?\n   10.188.244.1  2070    10.10.48.192 37184 0xCDE34A07 ITU-T G.711 PCMU  1103     0 (0.0%)           25.00            2.11            0.59 \n   10.10.48.192 37184    10.188.244.1  2070 0x65F27A72 ITU-T G.711 PCMU  1104     0 (0.0%)           25.00            3.65            1.98 \n  10.188.244.38  2048    10.188.244.1  2060 0xA1F5310D ITU-T G.711 PCMU  1104     0 (0.0%)           30.00            1.32            0.15 \n   10.188.244.1  2060   10.188.244.38  2048 0xEFC73AE0 ITU-T G.711 PCMU  1104     0 (0.0%)           25.00            2.08            0.63 \n==============================================================', bgw_number='004'),
#     '2025_12_20@13_12_33_003':
#     Capture(remote_ip='10.10.48.58', filename='2025_12_20@13_12_33_003', file_size=6539, received_timestamp=datetime(2025, 12, 20, 11, 9, 19, 319314), capinfos='File name:           uploads/2025_12_20@13_12_33_003\nFile type:           Wireshark/... - pcapng\nFile encapsulation:  Ethernet\nFile timestamp precision:  nanoseconds (9)\nPacket size limit:   file hdr: (not set)\nNumber of packets:   27 k\nFile size:           7,103 kB\nData size:           6,174 kB\nCapture duration:    199.353739380 second\nFirst packet time:   2025-11-26 11:24:14.684518725\nLast packet time:    2025-11-26 11:27:34.038258105\nData byte rate:      30 kBps\nData bit rate:       247 kbps\nAverage packet size: 225.95 bytes\nAverage packet rate: 137 packets/s\nSHA256:              0e7ff09bcbe5654e3c4eac48daae5d4bc3bc76350e9550fb89e4970ee4c4d4a8\nRIPEMD160:           4e7a1d5f0ada9bcfbc9208438aea108f656ece5d\nSHA1:                f9d5aed405f9702d4d8c16fb0546a6df7fb7e357\nStrict time order:   False\nCapture oper-sys:    64-bit Windows 11 (25H2), build 26200\nCapture application: Mergecap (Wireshark) 4.6.1 (v4.6.1-0-g291c718be4fe)\nCapture comment:     File created by merging:  File1: dc1voipsbc1_03439_20251126112414  File2: dc1voipsbc1_03440_20251126112449  File3: dc1voipsbc1_03441_20251126112520  File4: dc1voipsbc1_03442_20251126112554  File5: dc1voipsbc1_03443_20251126112630  File6: dc1voipsbc1_03444_20251126112703  \nNumber of interfaces in file: 2\nInterface #0 info:\n                     Name = A1\n                     Encapsulation = Ethernet (1 - ether)\n                     Capture length = 262144\n                     Time precision = nanoseconds (9)\n                     Time ticks per second = 1000000000\n                     Time resolution = 0x09\n                     Operating system = Linux 4.18.0-553.81.1.el8_10.x86_64\n                     Number of stat entries = 0\n                     Number of packets = 13403\nInterface #1 info:\n                     Name = B2\n                     Encapsulation = Ethernet (1 - ether)\n                     Capture length = 262144\n                     Time precision = nanoseconds (9)\n                     Time ticks per second = 1000000000\n                     Time resolution = 0x09\n                     Filter string = udp portrange 10000-40000 or port 5060\n                     BPF filter length = 0\n                     Operating system = Linux 4.18.0-553.81.1.el8_10.x86_64\n                     Number of stat entries = 0\n                     Number of packets = 13922', rtpinfos='========================= RTP Streams ========================\n    Src IP addr  Port    Dest IP addr  Port       SSRC          Payload  Pkts         Lost   Max Delta(ms)  Max Jitter(ms) Mean Jitter(ms) Problems?\n   10.234.255.5 36368      10.32.34.3 46750 0x2DC9D34B ITU-T G.711 PCMU  6618     0 (0.0%)          219.75            2.56            2.01 X\n     10.32.34.3 46750    10.234.255.5 36368 0x55063698 ITU-T G.711 PCMU  6624     0 (0.0%)          219.97            6.30            0.07 X\n162.248.168.235 49360     10.234.33.5 14344 0x2DC9D34B ITU-T G.711 PCMU  6620     0 (0.0%)           38.99            2.56            2.01 X\n    10.234.33.5 14344 162.248.168.235 49360 0x55063698 ITU-T G.711 PCMU  6624     0 (0.0%)           23.86            6.30            0.07 X\n     10.32.34.3 46750    10.234.255.5 38068 0x55063698 ITU-T G.711 PCMU    65     0 (0.0%)           20.26            0.09            0.06 \n    10.234.33.5 14344 162.248.168.235 46168 0x55063698 ITU-T G.711 PCMU    65     0 (0.0%)           20.26            0.09            0.06 \n   10.234.255.5 38068      10.32.34.3 46750 0x59A25729 ITU-T G.711 PCMU    68     0 (0.0%)           23.51            2.03            1.95 \n162.248.168.235 46168     10.234.33.5 14344 0x59A25729 ITU-T G.711 PCMU    68     0 (0.0%)           23.51            2.03            1.95 \n==============================================================', bgw_number='001')
    
# })

############################## BEGIN FUNCTIONS ###############################

def update_filter(group, filter, filter_groups=FILTER_GROUPs):
    args = vars(filter_parser.parse_args(filter.split()))
    
    if filter_groups.get(group) is not None:
        if args.get("no_filter"):
            filter_groups[group]["current_filter"] = ""
            filter_groups[group]["no_filter"] = args["no_filter"]
            logger.info(f"Cleared 'current_filter'")
    
        elif filter:
            filter_groups[group]["current_filter"] = filter
            logger.info(f"Updated 'current_filter' to '{filter}'")
    
        if filter_groups[group].get("groups") is not None:
            for key in filter_groups[group]["groups"]:
                if args.get(key) is not None:
                    if args.get("no_filter"):
                        filter_groups[group]["groups"][key].clear()
                    else:
                        filter_groups[group]["groups"][key] = args[key]
                    logger.info(f"Updated '{key}' to '{args[key]}'")

def hide_panel(ws):
    ws.active_panel.panel.hide()
    ws.active_panel = ws.panel
    ws.display.active_handle_char = ws.handle_char
    ws.bodywin.erase()
    ws.panel.top()
    ws.panel.show()
    ws.draw()
    curses.panel.update_panels()
    return 1

def discovery_start(ws):
    logger.info("Discovery start requested")
    
    is_canceled = make_filterpanel(ws, "bgw")
    if is_canceled:
        return

    if BGWs:
        GWs.clear()
        BGWs.clear()
        ws.win.erase()
        ws.draw()
        ws.win.refresh()


    ip_filter = FILTER_GROUPs["bgw"]["groups"]["ip_filter"]

    loop = startup_async_loop()
    fraction_queue = Queue(loop=loop)
    panel = ProgressBar(
        ws.display,
        queue=fraction_queue,
        workspace_chars = [ord("s"), ord("S")]
    )

    def discovery_callback(fraction):
        nonlocal fraction_queue, panel, ws
        fraction_queue.put_nowait(fraction)
        ws.menubar.draw()
        panel.draw()

    task = schedule_task(
        discovery(loop=loop, callback=discovery_callback, ip_filter=ip_filter),
        name="discovery",
        loop=loop,
    )

    def discovery_done_callback(fut):
        if fut.cancelled():
            return
        curses.flushinp()
        curses.ungetch(ord("s"))

    task.add_done_callback(discovery_done_callback)

    ws.panel.hide()
    ws.active_panel = panel
    ws.active_panel.draw()
    curses.panel.update_panels()

    ws.display.loop = loop
    ws.display.active_handle_char = panel.handle_char

    return panel

def discovery_stop(ws):
    logger.info("Discovery stop requested")
    
    loop = ws.display.loop

    if loop:
        ws.display.loop_shutdown_requested = True
        request_shutdown(loop)

    hide_panel(ws)

    return 1

def polling_start(ws):
    logger.info("Polling start requested")
    
    def process_item_callback():
        nonlocal ws
        if not ws.display.active_workspace.panel.hidden():
            ws.display.active_workspace.draw_bodywin()
        else:
            if ws.display.active_workspace.name == "RTPSTATS":
                show_rtp(ws.display.active_workspace)  
    
    loop = ws.display.loop

    if loop:
        return

    if not BGWs:
        return
    
    for bgw in BGWs.values():
        bgw.last_seen_dt = None

    loop = startup_async_loop()
    schedule_http_server(loop=loop)
    schedule_queries(loop=loop, bgws=BGWs, callback=process_item_callback)

    ws.display.loop = loop
    return 1

def polling_stop(ws):
    logger.info("Polling stop requested")
    
    loop = ws.display.loop

    if loop:
        ws.display.loop_shutdown_requested = True
        request_shutdown(loop)

    return 1

def capture_toggle(ws):
    if not ws.display.loop:
        return
    
    bgw = ws.storage.get(ws.storage_cursor + ws.body_posy)

    if "running" in bgw.capture_status:
        command = "capture stop"
        status = "stopping"
    elif "stopped" in bgw.capture_status:
        command = "capture start"
        status = "starting"
    else:
        return

    bgw.queue.put_nowait(command)
    bgw.packet_capture = status
    logger.info(f"PCAP {status} requested")

    if ws.active_panel == ws.panel:
        if not ws.display.active_workspace.panel.hidden():
            ws.display.active_workspace.draw_bodywin()
    return 1

def capture_upload(ws):
    if not ws.display.loop:
        return

    bgw = ws.storage.get(ws.storage_cursor + ws.body_posy)

    if bgw.pcap_upload == "requested":
        return
    
    http_server = "10.10.48.240" # config.get("http_server")
    http_port = config.get("http_port")
    upload_dir = config.get("upload_dir")
    dest = f"{http_server}:{http_port}/{upload_dir}"
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{bgw.bgw_number}.cap"
    
    command = f"copy capture-file https http://{dest}/{filename}"
    bgw.queue.put_nowait(command)
    bgw.pcap_upload = "requested"
    logger.info(f"PCAP upload '{command}' requested")

    if ws.active_panel == ws.panel:
        if not ws.display.active_workspace.panel.hidden():
            ws.display.active_workspace.draw_bodywin()
    return 1

def clear_storage(ws):

    if not ws.storage:
        return

    def clear_storage_callback(char):
        nonlocal ws
        if char in (ord("y"), ord("Y")):
            ws.storage.clear()
            if ws.storage.name == "BGWs":
                GWs.clear()

        hide_panel(ws)

    logger.info("Clear storage requested")
    panel = Confirmation(ws.display, callback=clear_storage_callback)

    ws.panel.hide()
    ws.active_panel = panel
    ws.active_panel.draw()
    curses.panel.update_panels()
    ws.display.active_handle_char = panel.handle_char

    return panel

def make_filterpanel(ws, group):
    
    if not group or FILTER_MENUs.get(group) is None:
        return

    logger.info("Make filterpanel requested")
    
    storage = FILTER_MENUs[group].splitlines()
    current = FILTER_GROUPs[ws.filter_group]["current_filter"]

    def filter_callback(filter):
        update_filter(group, filter)

    panel = FilterPanel(
        ws.display,
        storage = storage,
        current_filter = current,
        validator = filter_validator,
        callback = filter_callback,
        name = f"FilterPanel({group})"
    )
    panel.draw()
    is_canceled = panel.handle_char()
    return is_canceled

def make_textpanel(ws, *attr_names):
    bgw = ws.storage.get(ws.storage_cursor + ws.body_posy)

    if bgw is None:
        return

    logger.info("Make textpanel requested")

    storage = []
    for attr_name in attr_names:
        if not hasattr(bgw, attr_name):
            continue
        attr = str(getattr(bgw, attr_name)).strip()
        storage.extend([x.rstrip() for x in attr.splitlines()])

    if not storage:
        return

    panel = TextPanel(
        display = ws.display,
        storage = storage,
        name = f"TextPanel({attr})",
    )

    ws.menubar.draw()
    ws.panel.hide()
    ws.active_panel = panel
    ws.active_panel.draw()
    curses.panel.update_panels()
    curses.doupdate()
    ws.display.active_handle_char = panel.handle_char
    return panel

def show_system(ws):
    panel = make_textpanel(ws, "show_system")
    return panel if panel else None

def show_mg_list(ws):
    panel = make_textpanel(ws, "show_mg_list")
    return panel if panel else None

def show_port(ws):
    panel = make_textpanel(ws, "show_port")
    return panel if panel else None

def show_config(ws):
    panel = make_textpanel(ws, "show_running_config")
    return panel if panel else None

def show_status(ws):
    panel = make_textpanel(ws,
        "show_rtp_stat_summary",
        "show_voip_dsp",
        "show_utilization"
    )
    return panel if panel else None

def show_misc(ws):
    panel = make_textpanel(ws,
        "show_temp",
        "show_faults",
        "show_announcements_files"
    )
    return panel if panel else None

def show_pcap(ws):
    capture = ws.storage.get(ws.storage_cursor + ws.body_posy)

    if not capture:
        return

    logger.info("Show PCAP textpanel requested")
    
    panel = TextPanel(
        display = ws.display,
        storage = capture.rtpinfos.splitlines(),
        name = "TextPanel(PCAP)",
    )

    ws.menubar.draw()
    ws.panel.hide()
    ws.active_panel = panel
    ws.active_panel.draw()
    curses.panel.update_panels()
    curses.doupdate()
    ws.display.active_handle_char = panel.handle_char

    return panel

def show_rtp(ws):
    rtpdetailed = ws.storage.get(ws.storage_cursor + ws.body_posy)
    
    if not rtpdetailed:
        return

    logger.info("Show RTP objectpanel requested")

    panel = ObjectPanel(
        display=ws.display,
        obj=rtpdetailed,
        attr_iterator=iter_rtpdetailed,
        name = "ObjectPanel(RTP)"
    )

    ws.menubar.draw()
    ws.panel.hide()
    ws.active_panel = panel
    ws.active_panel.draw()
    ws.display.active_handle_char = panel.handle_char
    curses.panel.update_panels()
    curses.doupdate()#

    return panel

def main(stdscr, miny: int=24, minx: int=80):
    curses.start_color()
    curses.use_default_colors()

    def must_resize(stdscr, miny, minx):
        maxy, maxx = stdscr.getmaxyx()

        if maxy >= miny and maxx >= minx:
            return False

        lines = (
            f"Resize screen to  {miny}x{minx}",
            f"Current size      {maxy}x{maxx}",
            "Press 'q' to exit",
        )

        yoffset = max(0, maxy // 2 - 2)
        try:
            for i, line in enumerate(lines):
                xoffset = max(0, (maxx - len(line)) // 2)
                stdscr.addstr(yoffset + 2*i, xoffset, line)
        except curses.error:
            pass

        stdscr.box()
        stdscr.refresh()
        return True

    while must_resize(stdscr, miny, minx):
        char = stdscr.getch()
        if char == curses.ERR:
            time.sleep(0.1)
        elif char == curses.KEY_RESIZE:
            stdscr.erase()
        elif chr(char) in ("q", "Q"):
            return

    stdscr.erase()
    stdscr.refresh()
    stdscr.resize(miny, minx)

    mydisplay = MyDisplay(stdscr, miny=miny, minx=minx)

    button_discovery = Button(
        char_int = ord("s"),
        func_on = discovery_start,
        label_on = "Stop  Disc",
        label_off = "Start Disc",
        func_off = discovery_stop,
        status_label = "Discovery",
        status_color_on = 66304,
        status_color_off = 68096
    )

    button_polling = Button(
        char_int = ord("s"),
        func_on = polling_start,
        label_on = "Stop Poll",
        label_off = "Start Poll",
        func_off = polling_stop,
        status_label = " Polling ",
        status_color_on = 66304,
        status_color_off = 68096
    )

    button_clear_storage = Button(
        char_int = ord("c"),
        func_on = clear_storage,
        label_on = "Clear RTP",
        status_color_on = 66304,
        status_color_off = 68096
    )

    button_show_system = Button(
        char_int = ord("\n"),
        func_on = show_system,
        label_on = "Hide Panel",
        label_off = "Show More",
        func_off = hide_panel,
        status_color_on = 66304,
        status_color_off = 68096
    )

    button_show_misc = Button(
        char_int = ord("\n"),
        func_on = show_misc,
        label_on = "Hide Panel",
        label_off = "Show More",
        func_off = hide_panel,
        status_color_on = 66304,
        status_color_off = 68096
    )

    button_show_mg_list = Button(
        char_int = ord("\n"),
        func_on = show_mg_list,
        label_on = "Hide Panel",
        label_off = "Show More",
        func_off = hide_panel,
        status_color_on = 66304,
        status_color_off = 68096
    )

    button_show_port = Button(
        char_int = ord("\n"),
        func_on = show_port,
        label_on = "Hide Panel",
        label_off = "Show More",
        func_off = hide_panel,
        status_color_on = 66304,
        status_color_off = 68096
    )

    button_show_config = Button(
        char_int = ord("\n"),
        func_on = show_config,
        label_on = "Hide Panel",
        label_off = "Show More",
        func_off = hide_panel,
        status_color_on = 66304,
        status_color_off = 68096
    )

    button_show_pcap = Button(
        char_int = ord("\n"),
        func_on = show_pcap,
        label_on = "Hide Panel",
        label_off = "Show More",
        func_off = hide_panel,
        status_color_on = 66304,
        status_color_off = 68096
    )

    button_show_status = Button(
        char_int = ord("\n"),
        func_on = show_status,
        label_on = "Hide Panel",
        label_off = "Show More",
        func_off = hide_panel,
        status_color_on = 66304,
        status_color_off = 68096
    )

    button_show_rtp = Button(
        char_int = ord("\n"),
        func_on = show_rtp,
        label_on = "Hide Panel",
        label_off = "Show More",
        func_off = hide_panel,
        status_color_on = 66304,
        status_color_off = 68096
    )

    button_capture = Button(
        char_int = ord("t"),
        func_on = capture_toggle,
        label_on = "Toggle PCAP",
        status_color_on = 66304,
        status_color_off = 68096
    )

    button_upload = Button(
        char_int = ord("u"),
        func_on = capture_upload,
        label_on = "Upload PCAP",
        status_color_on = 66304,
        status_color_off = 68096
    )

    workspaces = [
        Workspace(
            mydisplay,
            screen=Screen(SCREENS["SYSTEM"]),
            buttons=[
                button_discovery,
                button_show_system
            ],
            storage=BGWs,
            name="SYSTEM",
            filter_group="bgw"
        ),
        Workspace(
            mydisplay,
            screen=Screen(SCREENS["MISC"]),
            buttons=[
                button_discovery,
                button_show_misc
            ],
            storage=BGWs,
            name="MISC",
            filter_group="bgw"
        ),
        Workspace(
            mydisplay,
            screen=Screen(SCREENS["MODULE"]),
            buttons=[
                button_discovery,
                button_show_mg_list
            ],
            storage=BGWs,
            name="MODULE",
            filter_group="bgw"
        ),
        Workspace(
            mydisplay,
            screen=Screen(SCREENS["PORT"]),
            buttons=[
                button_discovery,
                button_show_port
            ],
            storage=BGWs,
            name="PORT",
            filter_group="bgw"
        ),
        Workspace(
            mydisplay,
            screen=Screen(SCREENS["CONFIG"]),
            buttons=[
                button_discovery,
                button_show_config
            ],
            storage=BGWs,
            name="CONFIG",
            filter_group="bgw"
        ),
        Workspace(
            mydisplay,
            screen=Screen(SCREENS["STATUS"]),
            buttons=[
                button_polling,
                button_show_status,
                button_capture,
                button_upload
            ],
            storage=BGWs,
            name="STATUS",
        ),
        Workspace(
            mydisplay,
            screen=Screen(SCREENS["RTPSTATS"]),
            buttons=[
                button_polling,
                button_show_rtp,
                button_clear_storage
            ],
            storage=RTPs,
            name="RTPSTATS",
        ),
        Workspace(
            mydisplay,
            screen=Screen(SCREENS["PCAP"]),
            buttons=[
                button_show_pcap
            ],
            storage=PCAPs,
            name="PCAP",
            filter_group=None
        ),
    ]

    mydisplay.tab = Tab(mydisplay, tab_names=list(SCREENS.keys()))
    mydisplay.workspaces = workspaces
    mydisplay.run()

if __name__ == "__main__":
    with terminal_context("xterm-256color"):
        curses.wrapper(main)