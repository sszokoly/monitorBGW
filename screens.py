#!/usr/bin/env python
# -*- encoding: utf-8 -*-

############################## BEGIN IMPORTS #################################

import re
from typing import Any, Dict, Iterable, List, Tuple, Optional, Iterator, Generator, Callable

############################## END IMPORTS ###################################

from bgw import BGW
from storage import MemoryStorage
from rtpparser import parse_rtpstat
from datetime import datetime
from queue import Queue

bgw1 = BGW(**{'bgw_ip': '10.10.48.58', 'proto': 'ptls', 'polling_secs': 10, 'bgw_name': 'AvayaG450A', 'bgw_number': '001', 'polls': 1, 'avg_poll_secs': 10, 'active_session_ids': set(), 'last_seen': datetime(2025, 12, 16, 14, 33, 39), 'last_session_id': '', 'show_announcements_files': '\r\n ID      File               Description    Size (Bytes)      Date\r\n---- ------------------ ------------------ ------------ -------------------\r\n101   moh.wav            announcement file      239798    2022-08-23,8:45:26  \r\n102   emergency.wav      announcement file       26618    2023-03-24,11:36:10 \r\n103   public_announceme  announcement file      201914    2024-10-24,7:37:52  \r\n104   mohtest.wav        announcement file     9648106    2025-07-15,14:50:16 \r\n\r\nNv-Ram:\r\nTotal bytes used             : 10119680  \r\nTotal bytes free             : 12672000  \r\nTotal bytes capacity (fixed) : 22791680', 'show_capture': '\r\n\r\nCapture service is enabled and active\r\nCapture start time 09/12/2025-09:25:13\r\nCapture stop time not-stopped\r\nCurrent buffer size is 1024 KB\r\nBuffer mode is non-cyclic\r\nMaximum number of bytes captured from each frame: 4096\r\nCapture list 501 on all interfaces\r\nCapture IPSec decrypted\r\nNumber of captured frames in file: 604 (out of 145200 total captured frames)\r\nMemory buffer occupancy: 4.62% (including overheads)', 'show_faults': '\r\n\r\nCURRENTLY ACTIVE FAULTS\r\n--------------------------------------------------------------------------\r\n\r\n-- Media Module Faults --\r\n\t+ Insertion failure, mmid = v5, 11/24-07:37:04.00\r\n\r\nCurrent Alarm Indications, ALM LED is off\r\n--------------------------------------------------------------------------\r\nNone', 'show_lldp_config': '\r\n\r\nLldp Configuration \r\n-------------------\r\nApplication status: enable \r\nTx interval: 30 seconds\r\nTx hold multiplier: 4 seconds\r\nTx delay: 2 seconds\r\nReinit delay: 2 seconds', 'show_mg_list': '\r\nSLOT   TYPE         CODE        SUFFIX  HW VINTAGE  FW VINTAGE \r\n----   --------     ----------  ------  ----------  -----------\r\nv1     -- Not Installed --\r\nv2     -- Not Installed --\r\nv3     E1T1         MM710       B       16          52\r\nv4     -- Not Installed --\r\nv5     -- Initializing --\r\nv6     Analog       MM714       B       23          94\r\nv7     -- Not Installed --\r\nv8     -- Not Installed --\r\nv10    Mainboard    G450        B       2           42.36.0(A)', 'show_port': '\r\nPort   Name             Status    Vlan Level  Neg     Dup. Spd. Type\r\n------ ---------------- --------- ---- ------ ------- ---- ---- ----------------\r\n10/5   NO NAME          connected 1     0     enable  half 1G   Avaya Inc., G450 Media Gateway 10/100/1000BaseTx Port 10/5\r\n\r\n10/6   NO NAME          no link   1     0     enable  full 1G   Avaya Inc., G450 Media Gateway 10/100/1000BaseTx Port 10/6', 'show_rtp_stat_summary': '', 'show_running_config': '\r\n\r\n! version 42.36.0\r\nConfig info release 42.36.0 time "13:33:51 16 DEC 2025 " serial_number 10IS41452851\r\n !\r\nencrypted-username +ikJzwEP/t+XkAlH3l+zsw== password G6uSyomIZMSDb0NnT4RwvSb4IrSGUtuQ9ypCGFikR4w= access-type fe/kaDE5GWBC9Nfj6bNkgA==\r\n!\r\nencrypted-username mJ6sF5BOZeIUWsyCb3C1bw== password 8tMk4PMmywAU0cVXzSERF/aaj9WF0EAq4dB4c0qOLbU= access-type gf0PKwZMZRJ4zRba06ZC3w==\r\nhostname "AvayaG450A"\r\nset system location "Ontario Lab" \r\nno ip telnet \r\nip tftp-server file-system-size 2288\r\nset port mirror source-port 10/5 mirror-port 10/6 sampling always direction both\r\n!\r\nip capture-list 501\r\n name "udp"\r\n!\r\n ip-rule 1\r\n  ip-protocol udp\r\n exit\r\n ip-rule default\r\n  composite-operation "No-Capture"\r\n exit\r\n!\r\nexit\r\n!\r\nds-mode t1\r\n!\r\ninterface Vlan 1\r\n icc-vlan\r\n server-blade-vlan 5\r\n ip address 10.10.48.58     255.255.255.0  \r\n pmi\r\n exit\r\n!\r\ninterface FastEthernet 10/3\r\n exit\r\n!\r\ninterface FastEthernet 10/4\r\n exit\r\n!\r\ninterface Console\r\n speed 9600\r\n exit\r\n!\r\ninterface USB-Modem\r\n description "Default Modem Setup"\r\n timeout absolute 10\r\n ppp authentication ras\r\n no shutdown\r\n ip address 10.3.248.253    255.255.255.252\r\n exit\r\n!\r\ncapture max-frame-size 4096\r\ncapture buffer-mode non-cyclic\r\ncapture filter-group 501\r\nlogin authentication min-password-length 8\r\n!\r\nlogin authentication lockout 0 attempt 0\r\n! Avaya Login Confirmation Received.\r\nEASGManage enableEASG\r\nproduct-id 8c2ae2eead3e6cca800be892bb6e3411\r\n!\r\nset logging file enable \r\nset logging file condition all Error \r\nset logging file condition BOOT Debug \r\n!\r\nno snmp-server community \r\nencrypted-snmp-server user JSXE8Ccs0N0TnuoQek8jwLmaP391mjHjbt9glvbZ2M0= gAAa6QMAG08/c+A= v3ReadISO v3 auth sha 1FCIRMijXV+77fer97/S9O3FlfqIPrTOC5uTFcklYM8=  priv aes128 yyv5YmpCoEn5xZ24B7MR4Y03gnnqwygOY3eQTGRZZB0= \r\nencrypted-snmp-server user 0Ce9aP8Q25tEoXTe0YGwKmt2qLFQJ+UOpG6SMzseQdg= gAAa6QMAG08/c+A= v3TrapISO v3 auth sha TgX0mUpViHn56rSWounTurOYUdreS7rWWY7KssAnYj4=  priv aes128 p5Rdzsia/+4+Uc7f9oeJOj38gI6qX+2Fy1WDL5PTkh8= \r\nsnmp-server group v3ReadISO v3 priv read iso  \r\nsnmp-server group v3TrapISO v3 priv notify iso  \r\nsnmp-server host 10.10.48.92 traps v3 priv bbysnmpv3trap \r\n!\r\nip default-gateway 10.10.48.254    1 low  \r\n!\r\nset sync interface primary v3\r\nset sync source primary\r\nrtp-stat-service\r\nrtp-stat fault\r\nanalog-test\r\nexit\r\n!\r\nset sla-monitor enable\r\nset sla-server-ip-address 10.10.48.198\r\nudp keepalive 10\r\nset mgc list 10.10.48.240\r\nset mediaserver 10.10.48.240 10.10.48.240 23 telnet\r\nset mediaserver 10.10.48.240 10.10.48.240 5023 sat\r\n!#\r\n!# End of configuration file. Press Enter to continue.', 'show_sla_monitor': '\r\n\r\nSLA Monitor:                  Enabled\r\nRegistered Server IP Address: 192.111.111.111\r\nRegistered Server IP Port:    0\r\nConfigured Server IP Address: 10.10.48.198\r\nConfigured Server IP Port:    50011\r\nCapture Mode:                 None\r\nVersion:                      2.7.0', 'show_system': '\r\nSystem Name             : Ontario Lab\r\nSystem Location         : Ontario Lab\r\nSystem Contact          : \r\nUptime (d,h:m:s)        : 422,06:00:13\r\nCall Controller Time    : 13:33:56 16 DEC 2025 \r\nSerial No               : 13TG01116522\r\nModel                   : G430v3\r\nChassis HW Vintage      : 3\r\nChassis HW Suffix       : A\r\nMainboard HW Vintage    : 2\r\nMainboard HW Suffix     : B\r\nMainboard HW CS         : 2.1.7\r\nMainboard FW Vintage    : 42.36.0\r\nLAN MAC Address         : 00:1b:4f:3f:73:e0\r\nWAN1 MAC Address        : 00:1b:4f:3f:73:e1\r\nWAN2 MAC Address        : 00:1b:4f:3f:73:e2\r\nSERVICES MAC address    : 00:1b:4f:3f:73:e3\r\nMemory #1               : 256MB\r\nMemory #2               : Not present\r\nCompact Flash Memory    : 1GB Compact Flash card is installed\r\nPSU #1                  : AC 400W\r\nPSU #2                  : Not present\r\nMedia Socket #1         : MP160 VoIP DSP Module\r\nMedia Socket #2         : Not present\r\nMedia Socket #3         : Not present\r\nMedia Socket #4         : Not present\r\nFAN Tray                : Present', 'show_temp': '\r\nAmbient\r\n-------\r\nTemperature : -5C (23F)\r\nHigh Warning: 42C (108F)\r\nLow Warning : -5C (23F)', 'show_utilization': '\r\n\r\nMod   CPU      CPU     RAM      RAM\r\n      5sec     60sec   used(%)  Total(Kb)\r\n---   ------   -----  -------  ----------\r\n10    Appl. Disabled    48%     190838 Kb', 'show_voip_dsp': '\r\nDSP #1 PARAMETERS\r\n--------------------------------------------------------------\r\nBoard type     : MP160\r\nHw Vintage     : 0 B\r\nFw Vintage     : 182\r\n\r\nDSP#1 CURRENT STATE\r\n--------------------------------------------------------------\r\nIn Use         : 0 of 160 channels, 0 of 4800 points (0.0% used)\r\nState          : Idle\r\nAdmin State    : Release\r\n\r\nCore# Channels Admin     State\r\n      In Use   State\r\n----- -------- --------- -------\r\n    1  0 of 40   Release Idle\r\n    2  0 of 40   Release Idle\r\n    3  0 of 40   Release Idle\r\n    4  0 of 40   Release Idle\r\n\r\n\r\nDSP #2 Not Present\r\n\r\n\r\nDSP #3 Not Present\r\n\r\n\r\nDSP #4 Not Present', 'queue': Queue(), '_active_session': None, '_announcements': None, '_capture_service': None, '_chassis_hw': None, '_comp_flash': None, '_cpu_util': None, '_dsp': None, '_faults': None, '_fw': None, '_hw': None, '_inuse_dsp': None, '_last_seen_time': None, '_lldp': None, '_location': None, '_mac': None, '_mainboard_hw': None, '_memory': None, '_mm_groupdict': None, '_mm_v1': None, '_mm_v2': None, '_mm_v3': None, '_mm_v4': None, '_mm_v5': None, '_mm_v6': None, '_mm_v7': None, '_mm_v8': None, '_mm_v10': None, '_model': None, '_port1': None, '_port1_status': None, '_port1_neg': None, '_port1_duplex': None, '_port1_speed': None, '_port2': None, '_port2_status': None, '_port2_neg': None, '_port2_duplex': None, '_port2_speed': None, '_port_redu': None, '_psu1': None, '_psu2': None, '_ram_util': None, '_rtp_stat_service': None, '_serial': None, '_slamon_service': None, '_sla_server': None, '_snmp': None, '_snmp_trap': None, '_temp': None, '_total_session': None, '_uptime': None})
bgw2 = BGW(**{'bgw_ip': '10.10.48.59', 'proto': 'ptls', 'polling_secs': 10, 'bgw_name': 'AvayaG450B', 'bgw_number': '002', 'polls': 1, 'avg_poll_secs': 10, 'active_session_ids': set(), 'last_seen': datetime(2025, 12, 16, 14, 33, 39), 'last_session_id': '', 'show_announcements_files': '\r\n ID      File               Description    Size (Bytes)      Date\r\n---- ------------------ ------------------ ------------ -------------------\r\n101   moh.wav            announcement file      239798    2022-08-23,8:45:26  \r\n102   emergency.wav      announcement file       26618    2023-03-24,11:36:10 \r\n103   public_announceme  announcement file      201914    2024-10-24,7:37:52  \r\n104   mohtest.wav        announcement file     9648106    2025-07-15,14:50:16 \r\n\r\nNv-Ram:\r\nTotal bytes used             : 10119680  \r\nTotal bytes free             : 12672000  \r\nTotal bytes capacity (fixed) : 22791680', 'show_capture': '\r\n\r\nCapture service is enabled and active\r\nCapture start time 09/12/2025-09:25:13\r\nCapture stop time not-stopped\r\nCurrent buffer size is 1024 KB\r\nBuffer mode is non-cyclic\r\nMaximum number of bytes captured from each frame: 4096\r\nCapture list 501 on all interfaces\r\nCapture IPSec decrypted\r\nNumber of captured frames in file: 604 (out of 145200 total captured frames)\r\nMemory buffer occupancy: 4.62% (including overheads)', 'show_faults': '\r\n\r\nCURRENTLY ACTIVE FAULTS\r\n--------------------------------------------------------------------------\r\n\r\n-- Media Module Faults --\r\n\t+ Insertion failure, mmid = v5, 11/24-07:37:04.00\r\n\r\nCurrent Alarm Indications, ALM LED is off\r\n--------------------------------------------------------------------------\r\nNone', 'show_lldp_config': '\r\n\r\nLldp Configuration \r\n-------------------\r\nApplication status: disable \r\nTx interval: 30 seconds\r\nTx hold multiplier: 4 seconds\r\nTx delay: 2 seconds\r\nReinit delay: 2 seconds', 'show_mg_list': '\r\nSLOT   TYPE         CODE        SUFFIX  HW VINTAGE  FW VINTAGE \r\n----   --------     ----------  ------  ----------  -----------\r\nv1     -- Not Installed --\r\nv2     -- Not Installed --\r\nv3     E1T1         MM710       B       16          52\r\nv4     -- Not Installed --\r\nv5     -- Initializing --\r\nv6     Analog       MM714       B       23          94\r\nv7     -- Not Installed --\r\nv8     -- Not Installed --\r\nv10    Mainboard    G450        B       2           42.36.0(A)', 'show_port': '\r\nPort   Name             Status    Vlan Level  Neg     Dup. Spd. Type\r\n------ ---------------- --------- ---- ------ ------- ---- ---- ----------------\r\n10/5   NO NAME          connected 1     0     enable  full 1G   Avaya Inc., G450 Media Gateway 10/100/1000BaseTx Port 10/5\r\n\r\n10/6   NO NAME          connected   1     0     enable  half 10M   Avaya Inc., G450 Media Gateway 10/100/1000BaseTx Port 10/6', 'show_rtp_stat_summary': '', 'show_running_config': '\r\n\r\n! version 42.36.0\r\nConfig info release 42.36.0 time "13:33:51 16 DEC 2025 " serial_number 10IS41452851\r\n !\r\nencrypted-username +ikJzwEP/t+XkAlH3l+zsw== password G6uSyomIZMSDb0NnT4RwvSb4IrSGUtuQ9ypCGFikR4w= access-type fe/kaDE5GWBC9Nfj6bNkgA==\r\n!\r\nencrypted-username mJ6sF5BOZeIUWsyCb3C1bw== password 8tMk4PMmywAU0cVXzSERF/aaj9WF0EAq4dB4c0qOLbU= access-type gf0PKwZMZRJ4zRba06ZC3w==\r\nhostname "AvayaG450A"\r\nset system location "Calgary" \r\nno ip telnet \r\nip tftp-server file-system-size 2288\r\nset port mirror source-port 10/5 mirror-port 10/6 sampling always direction both\r\n!\r\nip capture-list 501\r\n name "udp"\r\n!\r\n ip-rule 1\r\n  ip-protocol udp\r\n exit\r\n ip-rule default\r\n  composite-operation "No-Capture"\r\n exit\r\n!\r\nexit\r\n!\r\nds-mode t1\r\n!\r\ninterface Vlan 1\r\n icc-vlan\r\n server-blade-vlan 5\r\n ip address 10.10.48.59     255.255.255.0  \r\n pmi\r\n exit\r\n!\r\ninterface FastEthernet 10/3\r\n exit\r\n!\r\ninterface FastEthernet 10/4\r\n exit\r\n!\r\ninterface Console\r\n speed 9600\r\n exit\r\n!\r\ninterface USB-Modem\r\n description "Default Modem Setup"\r\n timeout absolute 10\r\n ppp authentication ras\r\n no shutdown\r\n ip address 10.3.248.253    255.255.255.252\r\n exit\r\n!\r\ncapture max-frame-size 4096\r\ncapture buffer-mode non-cyclic\r\ncapture filter-group 501\r\nlogin authentication min-password-length 8\r\n!\r\nlogin authentication lockout 0 attempt 0\r\n! Avaya Login Confirmation Received.\r\nEASGManage enableEASG\r\nproduct-id 8c2ae2eead3e6cca800be892bb6e3411\r\n!\r\nset logging file enable \r\nset logging file condition all Error \r\nset logging file condition BOOT Debug \r\n!\r\nno snmp-server community \r\nencrypted-snmp-server user JSXE8Ccs0N0TnuoQek8jwLmaP391mjHjbt9glvbZ2M0= gAAa6QMAG08/c+A= v3ReadISO v3 auth sha 1FCIRMijXV+77fer97/S9O3FlfqIPrTOC5uTFcklYM8=  priv aes128 yyv5YmpCoEn5xZ24B7MR4Y03gnnqwygOY3eQTGRZZB0= \r\nencrypted-snmp-server user 0Ce9aP8Q25tEoXTe0YGwKmt2qLFQJ+UOpG6SMzseQdg= gAAa6QMAG08/c+A= v3TrapISO v3 auth sha TgX0mUpViHn56rSWounTurOYUdreS7rWWY7KssAnYj4=  priv aes128 p5Rdzsia/+4+Uc7f9oeJOj38gI6qX+2Fy1WDL5PTkh8= \r\nsnmp-server group v3ReadISO v3 priv read iso  \r\nsnmp-server group v3TrapISO v3 priv notify iso  \r\nsnmp-server host 10.10.48.92 traps v3 priv bbysnmpv3trap \r\n!\r\nip default-gateway 10.10.48.254    1 low  \r\n!\r\nset sync interface primary v3\r\nset sync source primary\r\nrtp-stat-service\r\nrtp-stat fault\r\nanalog-test\r\nexit\r\n!\r\nset sla-monitor enable\r\nset sla-server-ip-address 10.10.48.198\r\nudp keepalive 10\r\nset mgc list 10.10.48.240\r\nset mediaserver 10.10.48.240 10.10.48.240 23 telnet\r\nset mediaserver 10.10.48.240 10.10.48.240 5023 sat\r\n!#\r\n!# End of configuration file. Press Enter to continue.', 'show_sla_monitor': '\r\n\r\nSLA Monitor:                  Enabled\r\nRegistered Server IP Address: 0.0.0.0\r\nRegistered Server IP Port:    0\r\nConfigured Server IP Address: 10.10.48.198\r\nConfigured Server IP Port:    50011\r\nCapture Mode:                 None\r\nVersion:                      2.7.0', 'show_system': '\r\nSystem Name             : Calgary\r\nSystem Location         : Calgary\r\nSystem Contact          : \r\nUptime (d,h:m:s)        : 22,06:00:13\r\nCall Controller Time    : 13:33:56 16 DEC 2025 \r\nSerial No               : 13TG01116522\r\nModel                   : G450\r\nChassis HW Vintage      : 1\r\nChassis HW Suffix       : A\r\nMainboard HW Vintage    : 2\r\nMainboard HW Suffix     : B\r\nMainboard HW CS         : 2.1.7\r\nMainboard FW Vintage    : 42.36.0\r\nLAN MAC Address         : 00:1b:4f:3f:73:e8\r\nWAN1 MAC Address        : 00:1b:4f:3f:73:e1\r\nWAN2 MAC Address        : 00:1b:4f:3f:73:e2\r\nSERVICES MAC address    : 00:1b:4f:3f:73:e3\r\nMemory #1               : 256MB\r\nMemory #2               : Not present\r\nCompact Flash Memory    : No CompactFlash card is installed\r\nPSU #1                  : AC 400W\r\nPSU #2                  : Not present\r\nMedia Socket #1         : MP160 VoIP DSP Module\r\nMedia Socket #2         : Not present\r\nMedia Socket #3         : Not present\r\nMedia Socket #4         : Not present\r\nFAN Tray                : Present', 'show_temp': '\r\nAmbient\r\n-------\r\nTemperature : 42C (108F)\r\nHigh Warning: 42C (108F)\r\nLow Warning : -5C (23F)', 'show_utilization': '\r\n\r\nMod   CPU      CPU     RAM      RAM\r\n      5sec     60sec   used(%)  Total(Kb)\r\n---   ------   -----  -------  ----------\r\n10    Appl. Disabled    48%     190838 Kb', 'show_voip_dsp': '\r\nDSP #1 PARAMETERS\r\n--------------------------------------------------------------\r\nBoard type     : MP160\r\nHw Vintage     : 0 B\r\nFw Vintage     : 182\r\n\r\nDSP#1 CURRENT STATE\r\n--------------------------------------------------------------\r\nIn Use         : 0 of 160 channels, 0 of 4800 points (0.0% used)\r\nState          : Idle\r\nAdmin State    : Release\r\n\r\nCore# Channels Admin     State\r\n      In Use   State\r\n----- -------- --------- -------\r\n    1  0 of 40   Release Idle\r\n    2  0 of 40   Release Idle\r\n    3  0 of 40   Release Idle\r\n    4  0 of 40   Release Idle\r\n\r\n\r\nDSP #2 Not Present\r\n\r\n\r\nDSP #3 Not Present\r\n\r\n\r\nDSP #4 Not Present', 'queue': Queue(), '_active_session': None, '_announcements': None, '_capture_service': None, '_chassis_hw': None, '_comp_flash': None, '_cpu_util': None, '_dsp': None, '_faults': None, '_fw': None, '_hw': None, '_inuse_dsp': None, '_last_seen_time': None, '_lldp': None, '_location': None, '_mac': None, '_mainboard_hw': None, '_memory': None, '_mm_groupdict': None, '_mm_v1': None, '_mm_v2': None, '_mm_v3': None, '_mm_v4': None, '_mm_v5': None, '_mm_v6': None, '_mm_v7': None, '_mm_v8': None, '_mm_v10': None, '_model': None, '_port1': None, '_port1_status': None, '_port1_neg': None, '_port1_duplex': None, '_port1_speed': None, '_port2': None, '_port2_status': None, '_port2_neg': None, '_port2_duplex': None, '_port2_speed': None, '_port_redu': None, '_psu1': None, '_psu2': None, '_ram_util': None, '_rtp_stat_service': None, '_serial': None, '_slamon_service': None, '_sla_server': None, '_snmp': None, '_snmp_trap': None, '_temp': None, '_total_session': None, '_uptime': None})
bgw3 = BGW(**{'bgw_ip': '192.168.110.111', 'proto': 'ptls', 'polling_secs': 10, 'bgw_name': 'AvayaG450C', 'bgw_number': '003', 'polls': 1, 'avg_poll_secs': 10, 'active_session_ids': set(), 'last_seen': datetime(2025, 12, 16, 14, 33, 39), 'last_session_id': '', 'show_announcements_files': '\r\n ID      File               Description    Size (Bytes)      Date\r\n---- ------------------ ------------------ ------------ -------------------\r\n101   moh.wav            announcement file      239798    2022-08-23,8:45:26  \r\n102   emergency.wav      announcement file       26618    2023-03-24,11:36:10 \r\n103   public_announceme  announcement file      201914    2024-10-24,7:37:52  \r\n104   mohtest.wav        announcement file     9648106    2025-07-15,14:50:16 \r\n\r\nNv-Ram:\r\nTotal bytes used             : 10119680  \r\nTotal bytes free             : 12672000  \r\nTotal bytes capacity (fixed) : 22791680', 'show_capture': '\r\n\r\nCapture service is enabled and active\r\nCapture start time 09/12/2025-09:25:13\r\nCapture stop time not-stopped\r\nCurrent buffer size is 1024 KB\r\nBuffer mode is non-cyclic\r\nMaximum number of bytes captured from each frame: 4096\r\nCapture list 501 on all interfaces\r\nCapture IPSec decrypted\r\nNumber of captured frames in file: 604 (out of 145200 total captured frames)\r\nMemory buffer occupancy: 4.62% (including overheads)', 'show_faults': '\r\n\r\nNo Fault Messages\r\n--------------------------------------------------------------------------\r\nNone', 'show_lldp_config': '\r\n\r\nLldp Configuration \r\n-------------------\r\nApplication status: disable \r\nTx interval: 30 seconds\r\nTx hold multiplier: 4 seconds\r\nTx delay: 2 seconds\r\nReinit delay: 2 seconds', 'show_mg_list': '\r\nSLOT   TYPE         CODE        SUFFIX  HW VINTAGE  FW VINTAGE \r\n----   --------     ----------  ------  ----------  -----------\r\nv1     -- Not Installed --\r\nv2     -- Not Installed --\r\nv3     E1T1         MM710       B       16          52\r\nv4     -- Not Installed --\r\nv5     -- Initializing --\r\nv6     Analog       MM714       B       23          94\r\nv7     -- Not Installed --\r\nv8     -- Not Installed --\r\nv10    Mainboard    G450        B       2           42.36.0(A)', 'show_port': '\r\nPort   Name             Status    Vlan Level  Neg     Dup. Spd. Type\r\n------ ---------------- --------- ---- ------ ------- ---- ---- ----------------\r\n10/5   NO NAME          connected 1     0     enable  full 1G   Avaya Inc., G450 Media Gateway 10/100/1000BaseTx Port 10/5\r\n\r\n10/6   NO NAME          no link   1     0     enable  full 1G   Avaya Inc., G450 Media Gateway 10/100/1000BaseTx Port 10/6', 'show_rtp_stat_summary': '', 'show_running_config': '\r\n\r\n! version 42.36.0\r\nConfig info release 42.36.0 time "13:33:51 16 DEC 2025 " serial_number 10IS41452851\r\n !\r\nencrypted-username +ikJzwEP/t+XkAlH3l+zsw== password G6uSyomIZMSDb0NnT4RwvSb4IrSGUtuQ9ypCGFikR4w= access-type fe/kaDE5GWBC9Nfj6bNkgA==\r\n!\r\nencrypted-username mJ6sF5BOZeIUWsyCb3C1bw== password 8tMk4PMmywAU0cVXzSERF/aaj9WF0EAq4dB4c0qOLbU= access-type gf0PKwZMZRJ4zRba06ZC3w==\r\nhostname "AvayaG450A"\r\nset system location "Calgary" \r\nno ip telnet \r\nip tftp-server file-system-size 2288\r\nset port mirror source-port 10/5 mirror-port 10/6 sampling always direction both\r\n!\r\nip capture-list 501\r\n name "udp"\r\n!\r\n ip-rule 1\r\n  ip-protocol udp\r\n exit\r\n ip-rule default\r\n  composite-operation "No-Capture"\r\n exit\r\n!\r\nexit\r\n!\r\nds-mode t1\r\n!\r\ninterface Vlan 1\r\n icc-vlan\r\n server-blade-vlan 5\r\n ip address 10.10.48.60     255.255.255.0  \r\n pmi\r\n exit\r\n!\r\ninterface FastEthernet 10/3\r\n exit\r\n!\r\ninterface FastEthernet 10/4\r\n exit\r\n!\r\ninterface Console\r\n speed 9600\r\n exit\r\n!\r\ninterface USB-Modem\r\n description "Default Modem Setup"\r\n timeout absolute 10\r\n ppp authentication ras\r\n no shutdown\r\n ip address 10.3.248.253    255.255.255.252\r\n exit\r\n!\r\ncapture max-frame-size 4096\r\ncapture buffer-mode non-cyclic\r\ncapture filter-group 501\r\nlogin authentication min-password-length 8\r\n!\r\nlogin authentication lockout 0 attempt 0\r\n! Avaya Login Confirmation Received.\r\nEASGManage enableEASG\r\nproduct-id 8c2ae2eead3e6cca800be892bb6e3411\r\n!\r\nset logging file enable \r\nset logging file condition all Error \r\nset logging file condition BOOT Debug \r\n!\r\nno snmp-server community \r\nencrypted-snmp-server user JSXE8Ccs0N0TnuoQek8jwLmaP391mjHjbt9glvbZ2M0= gAAa6QMAG08/c+A= v3ReadISO v3 auth sha 1FCIRMijXV+77fer97/S9O3FlfqIPrTOC5uTFcklYM8=  priv aes128 yyv5YmpCoEn5xZ24B7MR4Y03gnnqwygOY3eQTGRZZB0= \r\nencrypted-snmp-server user 0Ce9aP8Q25tEoXTe0YGwKmt2qLFQJ+UOpG6SMzseQdg= gAAa6QMAG08/c+A= v3TrapISO v3 auth sha TgX0mUpViHn56rSWounTurOYUdreS7rWWY7KssAnYj4=  priv aes128 p5Rdzsia/+4+Uc7f9oeJOj38gI6qX+2Fy1WDL5PTkh8= \r\nsnmp-server group v3ReadISO v3 priv read iso  \r\nsnmp-server group v3TrapISO v3 priv notify iso  \r\nsnmp-server host 10.10.48.92 traps v3 priv bbysnmpv3trap \r\n!\r\nip default-gateway 10.10.48.254    1 low  \r\n!\r\nset sync interface primary v3\r\nset sync source primary\r\nrtp-stat-service\r\nrtp-stat fault\r\nanalog-test\r\nexit\r\n!\r\nset sla-monitor enable\r\nset sla-server-ip-address 10.10.48.198\r\nudp keepalive 10\r\nset mgc list 10.10.48.240\r\nset mediaserver 10.10.48.240 10.10.48.240 23 telnet\r\nset mediaserver 10.10.48.240 10.10.48.240 5023 sat\r\n!#\r\n!# End of configuration file. Press Enter to continue.', 'show_sla_monitor': '\r\n\r\nSLA Monitor:                 Disabled\r\nRegistered Server IP Address: 0.0.0.0\r\nRegistered Server IP Port:    0\r\nConfigured Server IP Address: 10.10.48.198\r\nConfigured Server IP Port:    50011\r\nCapture Mode:                 None\r\nVersion:                      2.7.0', 'show_system': '\r\nSystem Name             : \r\nSystem Location         : Calgary\r\nSystem Contact          : \r\nUptime (d,h:m:s)        : 22,06:00:13\r\nCall Controller Time    : 13:33:56 16 DEC 2025 \r\nSerial No               : 13TG01116522\r\nModel                   : G450\r\nChassis HW Vintage      : 1\r\nChassis HW Suffix       : A\r\nMainboard HW Vintage    : 2\r\nMainboard HW Suffix     : B\r\nMainboard HW CS         : 2.1.7\r\nMainboard FW Vintage    : 42.36.0\r\nLAN MAC Address         : 00:1b:4f:3f:73:e4\r\nWAN1 MAC Address        : 00:1b:4f:3f:73:e1\r\nWAN2 MAC Address        : 00:1b:4f:3f:73:e2\r\nSERVICES MAC address    : 00:1b:4f:3f:73:e4\r\nMemory #1               : 256MB\r\nMemory #2               : Not present\r\nCompact Flash Memory    : No CompactFlash card is installed\r\nPSU #1                  : AC 400W\r\nPSU #2                  : Not present\r\nMedia Socket #1         : MP160 VoIP DSP Module\r\nMedia Socket #2         : Not present\r\nMedia Socket #3         : Not present\r\nMedia Socket #4         : Not present\r\nFAN Tray                : Present', 'show_temp': '\r\nAmbient\r\n-------\r\nTemperature : 36C (97F)\r\nHigh Warning: 42C (108F)\r\nLow Warning : -5C (23F)', 'show_utilization': '\r\n\r\nMod   CPU      CPU     RAM      RAM\r\n      5sec     60sec   used(%)  Total(Kb)\r\n---   ------   -----  -------  ----------\r\n10    Appl. Disabled    48%     190838 Kb', 'show_voip_dsp': '\r\nDSP #1 PARAMETERS\r\n--------------------------------------------------------------\r\nBoard type     : MP160\r\nHw Vintage     : 0 B\r\nFw Vintage     : 182\r\n\r\nDSP#1 CURRENT STATE\r\n--------------------------------------------------------------\r\nIn Use         : 0 of 160 channels, 0 of 4800 points (0.0% used)\r\nState          : Idle\r\nAdmin State    : Release\r\n\r\nCore# Channels Admin     State\r\n      In Use   State\r\n----- -------- --------- -------\r\n    1  0 of 40   Release Idle\r\n    2  0 of 40   Release Idle\r\n    3  0 of 40   Release Idle\r\n    4  0 of 40   Release Idle\r\n\r\n\r\nDSP #2 Not Present\r\n\r\n\r\nDSP #3 Not Present\r\n\r\n\r\nDSP #4 Not Present', 'queue': Queue(), '_active_session': None, '_announcements': None, '_capture_service': None, '_chassis_hw': None, '_comp_flash': None, '_cpu_util': None, '_dsp': None, '_faults': None, '_fw': None, '_hw': None, '_inuse_dsp': None, '_last_seen_time': None, '_lldp': None, '_location': None, '_mac': None, '_mainboard_hw': None, '_memory': None, '_mm_groupdict': None, '_mm_v1': None, '_mm_v2': None, '_mm_v3': None, '_mm_v4': None, '_mm_v5': None, '_mm_v6': None, '_mm_v7': None, '_mm_v8': None, '_mm_v10': None, '_model': None, '_port1': None, '_port1_status': None, '_port1_neg': None, '_port1_duplex': None, '_port1_speed': None, '_port2': None, '_port2_status': None, '_port2_neg': None, '_port2_duplex': None, '_port2_speed': None, '_port_redu': None, '_psu1': None, '_psu2': None, '_ram_util': None, '_rtp_stat_service': None, '_serial': None, '_slamon_service': None, '_sla_server': None, '_snmp': None, '_snmp_trap': None, '_temp': None, '_total_session': None, '_uptime': None})
BGWS = MemoryStorage({'10.10.48.58': bgw1, '10.10.48.59': bgw2, '192.168.110.111': bgw3})
GWs = {'10.10.48.58': "001", "10.10.48.59": "002", "192.168.110.111": "003", "10.44.244.51": "004"}

STORAGE = MemoryStorage()
d = {
    "2024-11-04,10:06:07,001,00001": "\r\nshow rtp-stat detailed 00001\r\n\r\nSession-ID: 1\r\nStatus: Terminated, QOS: Faulted, EngineId: 10\r\nStart-Time: 2024-11-04,10:06:07, End-Time: 2024-11-04,10:07:07\r\nDuration: 00:02:00\r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.111:2052 SSRC 1653399062\r\nRemote-Address: 10.10.48.192:35000 SSRC 2704961869 (0)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG729A 200B 20mS srtpAesCm128HmacSha180, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 4.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 0.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 1243, Loss 0.3% #0, Avg-Loss 0.3%, RTT 0mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 0, Seq-Fall 1, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 0, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 0.0% #0, Avg-Loss 0.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n",
    "2025-12-14,10:07:27,002,00002": "\r\nshow rtp-stat detailed 00002\r\n\r\nSession-ID: 1\r\nStatus: Active, QOS: Ok, EngineId: 10\r\nStart-Time: 2025-12-14,10:07:27, End-Time: -\r\nDuration: - \r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.112:2052 SSRC 1653399062\r\nRemote-Address: 10.10.48.192:35000 SSRC 2704961869 (0)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG711U 200B 20mS srtpAesCm128HmacSha180, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 334.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 0.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 123, Loss 0.3% #0, Avg-Loss 0.3%, RTT 0mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 2, Seq-Fall 0, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 46, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 2.0% #0, Avg-Loss 1.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n",
    "2025-12-14,10:08:07,003,00001": "\r\nshow rtp-stat detailed 00001\r\n\r\nSession-ID: 1\r\nStatus: Active, QOS: Ok, EngineId: 10\r\nStart-Time: 2025-12-14,10:08:07, End-Time: 2025-12-14,10:08:22\r\nDuration: 00:12:20\r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.113:2056 SSRC 1653399062\r\nRemote-Address: 192.168.110.111:35001 SSRC 2704961869 (0)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG711U 230B 30mS Off, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 334.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 1.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 0, Loss 0.3% #0, Avg-Loss 0.3%, RTT 0mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 0, Seq-Fall 0, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 46, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 0.0% #0, Avg-Loss 0.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n",

}

for global_id, value in d.items():
        rtpdetailed = parse_rtpstat(global_id, value)
        STORAGE.put({global_id: rtpdetailed})

############################## BEGIN VARIABLES ################################

"""
SYSTEM
          1         2         3         4         5         6         7
01234567890123456789012345678901234567890123456789012345678901234567890123456789
+---+--------------+---------------+------------+------------+-----+--+--------+
│BGW│     Name     |     LAN IP    │  LAN MAC   | Serial No. |Model│HW│Firmware│
+---+--------------+---------------+------------+------------+-----+--+--------+
|001|              |192.168.111.111|123456789ABC|13TG01116522| g430│1A│43.11.12│
+---+--------------+---------------+------------+------------+-----+--+--------+

MISC
          1         2         3         4         5         6         7
01234567890123456789012345678901234567890123456789012345678901234567890123456789
+---+------------+--------+-------------+-----+----+------+---+----+-----+-----+
│BGW│  Location  |  Temp  |    Uptime   |Chass|Main|Memory│DSP│Anno|Flash|Fault|
+---+------------+--------+-------------+-----+----+------+---+----+-----+-----+
|001|            |42C/108F|153d05h23m06s|   1A|  3A| 256MB│160│ 999|  1GB|    4|
+---+------------+--------+-------------+-----+----+------+---+----+-----+-----+

MODULE
          1         2         3         4         5         6         7
01234567890123456789012345678901234567890123456789012345678901234567890123456789
+---+------+------+------+------+------+------+------+------+--------+----+----+
│BGW│  v1  |  v2  |  v3  |  v4  |  v5  |  v6  |  v7  |  v8  | v10 hw |PSU1|PSU2|
+---+------+------+------+------+------+------+------+------+--------+----+----+
|001|S8300E│MM714B│MM714B│MM714B│MM714B│MM714B│MM714B│MM714B│      3A|400W│400W|
+---+------+------+------+------+------+------+------+------+--------+----+----+

PORT
          1         2         3         4         5         6         7
01234567890123456789012345678901234567890123456789012345678901234567890123456789
+---+-----+---------+--------+---------+-----+---------+--------+----+----+----+
|BGW|Port1| Status1 |  Neg1  |Spd1|Dup1|Port2| Status2 |  Neg2  |Spd2|Dup2|Redu|
+---+-----+---------+--------+----+----+-----+---------+--------+----+----+----+
|001| 10/4|connected| enabled|100M|full| 10/5|  no link| enabled|100M|half| 5/4|
+---+-----+---------+--------+----+----+-----+---------+--------+----+----+----+

CONFIG
          1         2         3         4         5         6         7
01234567890123456789012345678901234567890123456789012345678901234567890123456789
+---+--------+-----------------+----+--------+--------+---------------+--------+
|BGW|RTP-Stat| Capture-Service |SNMP|SNMPTrap| SLAMon | SLAMon Server |  LLDP  |
+---+--------+-----------------+----+--------+--------+---------------+--------+
|001|disabled| enabled/inactive|v2&3|disabled|disabled|101.101.111.198|disabled|
+---+--------+-----------------+----+--------+--------+---------------+--------+

PCAP
          1         2         3         4         5         6         7
01234567890123456789012345678901234567890123456789012345678901234567890123456789
+---+--------------------------+-------------------+-------------------+-------+
|BGW|          Filename        |    First Packet   |    Last Packet    |RTP|NOK| 
+---+--------------------------+-------------------+-------------------+---+---+
|001|   2025_12_19@22_05_45_001|2025-11-26 11:27:34|2025-11-26 11:27:35|  3|  1|
+---+--------------------------+-------------------+-------------------+---+---+

STATUS
          1         2         3         4         5         6         7
01234567890123456789012345678901234567890123456789012345678901234567890123456789
+---+--------+-------+-------+-----+--------+--------------+----------+--------+
|BGW|Act.Sess|Act.DSP|CPU 60s| RAM |Avg.Poll|Packet Capture|PCAP Dwnld|LastSeen|
+---+--------+-------+-------+-----+--------+--------------+----------+--------+
|001|     0/0|    320|   100%|  45%|    120s| running (54%)| executing|11:02:11|
+---+--------+-------+-------+-----+--------+--------------+----------+--------+

RTPSTATS
          1         2         3         4         5         6         7
01234567890123456789012345678901234567890123456789012345678901234567890123456789
+---+--------+--------+---------------+-----+---------------+-----+-------+----+
|BGW|  Start |   End  | Local-Address |LPort| Remote-Address|RPort| Codec | OK?|
+---+--------+--------+---------------+-----+---------------+-----+-------+----+
|001|11:09:07|11:11:27|192.168.111.111|55555|100.100.100.100|55555| G711U |  X |
+---+--------+--------+---------------+-----+---------------+-----+-------+----+
"""

LAYOUTS = {
    "SYSTEM": [
        ("BGW", {
            "attr_name": "bgw_number",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">3",
            "attr_xpos": 1,
        }),
        ("Name", {
            "attr_name": "bgw_name",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">14",
            "attr_xpos": 5,
        }),
        ("LAN IP", {
            "attr_name": "bgw_ip",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">15",
            "attr_xpos": 20,
        }),
        ("LAN MAC", {
            "attr_name": "mac",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">12",
            "attr_xpos": 36,
        }),
        ("Serial No.", {
            "attr_name": "serial",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">12",
            "attr_xpos": 49,
        }),
        ("Model", {
            "attr_name": "model",
            "attr_func": lambda x: x[:4],
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">5",
            "attr_xpos": 62,
        }),
        ("HW", {
            "attr_name": "hw",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">2",
            "attr_xpos": 68,
        }),
        ("Firmware", {
            "attr_name": "fw",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">8",
            "attr_xpos": 71,
        }),
    ],
    "MISC": [
        ("BGW", {
            "attr_name": "bgw_number",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">3",
            "attr_xpos": 1,
        }),
        ("Location", {
            "attr_name": "location",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">12",
            "attr_xpos": 5,
        }),
        ("Temp", {
            "attr_name": "temp",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal"
                if x[:2].isdigit() and int(x[:2]) >= 42
                else "attr_color"
            ),
            "attr_fmt": ">8",
            "attr_xpos": 18,
        }),
        ("Uptime", {
            "attr_name": "uptime",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">13",
            "attr_xpos": 27,
        }),
        ("Chass", {
            "attr_name": "chassis_hw",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">5",
            "attr_xpos": 41,
        }),
        ("Main", {
            "attr_name": "mainboard_hw",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">4",
            "attr_xpos": 47,
        }),
        ("Memory", {
            "attr_name": "memory",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">6",
            "attr_xpos": 52,
        }),
        ("DSP", {
            "attr_name": "dsp",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">3",
            "attr_xpos": 59,
        }),
        ("Anno", {
            "attr_name": "announcements",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">4",
            "attr_xpos": 63,
        }),
        ("Flash", {
            "attr_name": "comp_flash",
            "attr_func": lambda x: x[:5],
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">5",
            "attr_xpos": 68,
        }),
        ("Fault", {
            "attr_name": "faults",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x.strip() != "0" else "attr_color"
            ),
            "attr_fmt": ">5",
            "attr_xpos": 74,
        }),
    ],
    "MODULE": [
        ("BGW", {
            "attr_name": "bgw_number",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x.startswith("Init") else "attr_color"
            ),
            "attr_fmt": ">3",
            "attr_xpos": 1,
        }),
        ("v1", {
            "attr_name": "mm_v1",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x.startswith("Init") else "attr_color"
            ),
            "attr_fmt": "<6",
            "attr_xpos": 5,
        }),
        ("v2", {
            "attr_name": "mm_v2",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x.startswith("Init") else "attr_color"
            ),
            "attr_fmt": "<6",
            "attr_xpos": 12,
        }),
        ("v3", {
            "attr_name": "mm_v3",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x.startswith("Init") else "attr_color"
            ),
            "attr_fmt": "<6",
            "attr_xpos": 19,
        }),
        ("v4", {
            "attr_name": "mm_v4",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x.startswith("Init") else "attr_color"
            ),
            "attr_fmt": "<6",
            "attr_xpos": 26,
        }),
        ("v5", {
            "attr_name": "mm_v5",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x.startswith("Init") else "attr_color"
            ),
            "attr_fmt": "<6",
            "attr_xpos": 33,
        }),
        ("v6", {
            "attr_name": "mm_v6",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x.startswith("Init") else "attr_color"
            ),
            "attr_fmt": "<6",
            "attr_xpos": 40,
        }),
        ("v7", {
            "attr_name": "mm_v7",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x.startswith("Init") else "attr_color"
            ),
            "attr_fmt": "<6",
            "attr_xpos": 47,
        }),
        ("v8", {
            "attr_name": "mm_v8",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x.startswith("Init") else "attr_color"
            ),
            "attr_fmt": "<6",
            "attr_xpos": 54,
        }),
        ("v10 hw", {
            "attr_name": "mm_v10",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">8",
            "attr_xpos": 61,
        }),
        ("PSU1", {
            "attr_name": "psu1",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">4",
            "attr_xpos": 70,
        }),
        ("PSU2", {
            "attr_name": "psu2",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">4",
            "attr_xpos": 75,
        }),
    ],
    "PORT": [
        ("BGW", {
            "attr_name": "bgw_number",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">3",
            "attr_xpos": 1,
        }),
        ("Port1", {
            "attr_name": "port1",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">5",
            "attr_xpos": 5,
        }),
        ("Status1", {
            "attr_name": "port1_status",
            "attr_func": None,
            "attr_color": "connected",
            "color_func": lambda x: (
                "anormal" if "no link" in x else "attr_color"
            ),
            "attr_fmt": ">9",
            "attr_xpos": 11,
        }),
        ("Neg1", {
            "attr_name": "port1_neg",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">8",
            "attr_xpos": 21,
        }),
        ("Spd1", {
            "attr_name": "port1_speed",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">4",
            "attr_xpos": 30,
        }),
        ("Dup1", {
            "attr_name": "port1_duplex",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "attr_color" if "full" in x else "anormal"
            ),
            "attr_fmt": ">4",
            "attr_xpos": 35,
        }),
        ("Port2", {
            "attr_name": "port2",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">5",
            "attr_xpos": 40,
        }),
        ("Status2", {
            "attr_name": "port2_status",
            "attr_func": None,
            "attr_color": "connected",
            "color_func": lambda x: (
                "anormal" if "no link" in x else "attr_color"
            ),
            "attr_fmt": ">9",
            "attr_xpos": 46,
        }),
        ("Neg2", {
            "attr_name": "port2_neg",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">8",
            "attr_xpos": 56,
        }),
        ("Spd2", {
            "attr_name": "port2_speed",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">4",
            "attr_xpos": 65,
        }),
        ("Dup2", {
            "attr_name": "port2_duplex",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "attr_color" if "full" in x else "anormal"
            ),
            "attr_fmt": ">4",
            "attr_xpos": 70,
        }),
        ("Redu", {
            "attr_name": "port_redu",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">4",
            "attr_xpos": 75,
        }),
    ],
    "CONFIG": [
        ("BGW", {
            "attr_name": "bgw_number",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "attr_color" if x else "anormal"
            ),
            "attr_fmt": ">3",
            "attr_xpos": 1,
        }),
        ("RTP-Stats", {
            "attr_name": "rtp_stat_service",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if "disabled" in x else "attr_color"
            ),
            "attr_fmt": ">8",
            "attr_xpos": 5,
        }),
        ("Capture-Service", {
            "attr_name": "capture_service",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if "disabled" in x else "attr_color"
            ),
            "attr_fmt": ">17",
            "attr_xpos": 14,
        }),
        ("SNMP", {
            "attr_name": "snmp",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">4",
            "attr_xpos": 32,
        }),
        ("SNMPTrap", {
            "attr_name": "snmp_trap",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">8",
            "attr_xpos": 37,
        }),
        ("SLAMon", {
            "attr_name": "slamon_service",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">8",
            "attr_xpos": 46,
        }),
        ("SLAMon Server", {
            "attr_name": "sla_server",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">15",
            "attr_xpos": 55,
        }),
        ("LLDP", {
            "attr_name": "lldp",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">8",
            "attr_xpos": 71,
        }),
    ],
    "STATUS": [
        ("BGW", {
            "attr_name": "bgw_number",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">3",
            "attr_xpos": 1,
        }),
        ("Act.Sess", {
            "attr_name": "active_session",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">8",
            "attr_xpos": 5,
        }),
        ("Act.DSP", {
            "attr_name": "inuse_dsp",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">7",
            "attr_xpos": 14,
        }),
        ("CPU", {
            "attr_name": "cpu_util",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">5",
            "attr_xpos": 22,
        }),
        ("RAM", {
            "attr_name": "ram_util",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">5",
            "attr_xpos": 28,
        }),
        ("Avg.Poll", {
            "attr_name": "avg_poll_secs",
            "attr_func": lambda x: str(x) + "s",
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">8",
            "attr_xpos": 34,
        }),
        ("Packet Capture", {
            "attr_name": "packet_capture",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x.strip() in ("starting", "stopping") else "attr_color"
            ),
            "attr_fmt": ">14",
            "attr_xpos": 43,
        }),
        ("Capture Upld", {
            "attr_name": "pcap_upload",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x.strip() == "requested" else "attr_color"
            ),
            "attr_fmt": ">12",
            "attr_xpos": 58,
        }),
        ("LastSeen", {
            "attr_name": "last_seen_time",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">8",
            "attr_xpos": 71,
        }),
    ],
    "RTPSTATS": [
        ("BGW", {
            "attr_name": "bgw_number",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: "attr_color" if x else "anormal",
            "attr_fmt": ">3",
            "attr_xpos": 1,
        }),
        ("Start", {
            "attr_name": "start_time",
            "attr_func": lambda x: x[-8:],
            "attr_color": "normal",
            "color_func": lambda x: "attr_color" if x else "anormal",
            "attr_fmt": "^8",
            "attr_xpos": 5,
        }),
        ("End", {
            "attr_name": "end_time",
            "attr_func": lambda x: x[-8:],
            "attr_color": "normal",
            "color_func": lambda x: "attr_color" if x else "anormal",
            "attr_fmt": "^8",
            "attr_xpos": 14,
        }),
        ("Local-Address", {
            "attr_name": "local_addr",
            "attr_func": None,
            "attr_color": "is_bgw_ip",
            "color_func": lambda x: "attr_color" if x else "anormal",
            "attr_fmt": ">15",
            "attr_xpos": 23,
        }),
        ("LPort", {
            "attr_name": "local_port",
            "attr_func": None,
            "attr_color": "port",
            "color_func": lambda x: (
                "attr_color" if x and int(x) % 2 == 0 else "odd"
            ),
            "attr_fmt": ">5",
            "attr_xpos": 39,
        }),
        ("Remote-Address", {
            "attr_name": "remote_addr",
            "attr_func": None,
            "attr_color": "address",
            "color_func": lambda x: (
                "is_bgw_ip" if x and x in BGWS else "attr_color"
            ),
            "attr_fmt": ">15",
            "attr_xpos": 45,
        }),
        ("RPort", {
            "attr_name": "remote_port",
            "attr_func": None,
            "attr_color": "port",
            "color_func": lambda x: (
                "attr_color" if x and int(x) % 2 == 0 else "odd"
            ),
            "attr_fmt": ">5",
            "attr_xpos": 61,
        }),
        ("Codec", {
            "attr_name": "codec",
            "attr_func": None,
            "attr_color": "codec",
            "color_func": lambda x: (
                "attr_color" if x.startswith("G711") else "notg711"
            ),
            "attr_fmt": "^7",
            "attr_xpos": 67,
        }),
        (" OK?", {
            "attr_name": "nok",
            "attr_func": lambda x: (u" ❌" if x == "Zero"
                                    else (u" ⚠️" if x == "QoS" else u" ✅")),
            "attr_color": "normal",
            "color_func": lambda x: "anormal" if x != "None" else "attr_color",
            "attr_fmt": "<4",
            "attr_xpos": 75,
        }),
    ],
    "PCAP": [
        ("BGW", {
            "attr_name": "bgw_number",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">3",
            "attr_xpos": 1,
        }),
        ("Filename", {
            "attr_name": "filename",
            "attr_func": lambda x: x[-26:],
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">26",
            "attr_xpos": 5,
        }),
        ("First Packet", {
            "attr_name": "first_packet_time",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">19",
            "attr_xpos": 32,
        }),
        ("Last Packet", {
            "attr_name": "last_packet_time",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">19",
            "attr_xpos": 52,
        }),
        ("RTP", {
            "attr_name": "rtp_streams",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">3",
            "attr_xpos": 72,
        }),
        ("NOK", {
            "attr_name": "rtp_problems",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x and int(x) > 0 else "attr_color"
            ),
            "attr_fmt": ">3",
            "attr_xpos": 76,
        }),
    ],
}

"""       1         2         3         4         5         6         7
01234567890123456789012345678901234567890123456789012345678901234567890123456789
+------------------------------------------------------------------------------+
|Session-ID: 42      Status: Terminated    QoS: OK        Samples: 234         |
|Start: 11:09:07              End: 11:11:27              Duration: 00:02:20    |
|                                                                              |
|              LOCAL                                     REMOTE                |
|    192.168.111.111:55555 <--------------------> 55555:100.100.100.100        |
|      SSRC 0x12ab34cd   Enc:        G711U            SSRC 0x98fe76aa (0)      |
|                                                                              |
|             RTP/RTCP                                   CODEC                 |
| RTP Packets (Rx/Tx):  12345 /    NA         Psize/Ptime:    160/20           |
|RTCP Packets (Rx/Tx):    123 /    45           Play-Time:  00:02:20           |
|        DSCP (Rx/Tx):     46 /    46            Avg-Loss:   1.1%              |
|       L2Pri (Rx/Tx):      5 /     5             Avg-RTT:    123              |
|     Duplicates (Rx):      0              Max-Jbuf-Delay:     42              |
|       Seq-Fall (Rx):      0           JBuf-und/overruns:      1/0            |
|                                                                              |
|        LOCAL RTP STATISTICS                    REMOTE RTP STATISTICS         |
|            Avg-Loss:   1.1%                    Avg-Loss:   1.1%              |
|          Avg-Jitter:      3                  Avg-Jitter:      7              |
|             Avg-RTT:    123                                                  |
|                                                                              |
+------------------------------------------------------------------------------+
"""

RTP_LAYOUT = [
    (
        "Session-ID:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 1,
            "attr_xpos": 1,
        },
    ),
    (
        "session_id",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 1,
            "attr_xpos": 13,
        },
    ),
    (
        "Status:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 1,
            "attr_xpos": 21,
        },
    ),
    (
        "status",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "bold" if "Active" in x else "attr_color"
            ),
            "attr_fmt": "",
            "attr_ypos": 1,
            "attr_xpos": 29,
        },
    ),
    (
        "QoS:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 1,
            "attr_xpos": 43,
        },
    ),
    (
        "qos",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if "Faulted" in x else "attr_color"
            ),
            "attr_fmt": "",
            "attr_ypos": 1,
            "attr_xpos": 48,
        },
    ),
    (
        "Samples:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 1,
            "attr_xpos": 58,
        },
    ),
    (
        "samples",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 1,
            "attr_xpos": 67,
        },
    ),
    (
        "Start:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 2,
            "attr_xpos": 1,
        },
    ),
    (
        "start_time",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 2,
            "attr_xpos": 8,
        },
    ),
    (
        "End:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 2,
            "attr_xpos": 30,
        },
    ),
    (
        "end_time",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 2,
            "attr_xpos": 35,
        },
    ),
    (
        "Duration:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 2,
            "attr_xpos": 57,
        },
    ),
    (
        "duration",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 2,
            "attr_xpos": 67,
        },
    ),
    (
        "LOCAL",
        {
            "attr_func": None,
            "attr_color": "title",
            "color_func": None,
            "attr_fmt": "^36",
            "attr_ypos": 4,
            "attr_xpos": 1,
        },
    ),
    (
        "REMOTE",
        {
            "attr_func": None,
            "attr_color": "title",
            "color_func": None,
            "attr_fmt": "^36",
            "attr_ypos": 4,
            "attr_xpos": 40,
        },
    ),
    (
        "local_addr",
        {
            "attr_func": None,
            "attr_color": "is_bgw_ip",
            "color_func": None,
            "attr_fmt": ">15",
            "attr_ypos": 5,
            "attr_xpos": 5,
        },
    ),
    (
        ":",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 5,
            "attr_xpos": 20,
        },
    ),
    (
        "local_port",
        {
            "attr_func": None,
            "attr_color": "port",
            "color_func": lambda x: (
                "attr_color" if x.strip().isdigit() and int(x.strip()) % 2 == 0
                else "odd"
            ),
            "attr_fmt": "<5",
            "attr_ypos": 5,
            "attr_xpos": 21,
        },
    ),
    (
        "<",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 5,
            "attr_xpos": 27,
        },
    ),
    (
        "-",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "-^20",
            "attr_ypos": 5,
            "attr_xpos": 28,
        },
    ),
    (
        "codec",
        {
            "attr_func": None,
            "attr_color": "codec",
            "color_func": lambda x: (
                "attr_color" if x.strip().startswith("G711") else "notg711"
            ),
            "attr_fmt": "^7",
            "attr_ypos": 5,
            "attr_xpos": 35,
        },
    ),
    (
        ">",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 5,
            "attr_xpos": 48,
        },
    ),
    (
        "remote_port",
        {
            "attr_func": None,
            "attr_color": "port",
            "color_func": lambda x: (
                "attr_color" if x.strip().isdigit() and int(x.strip()) % 2 == 0
                else "odd"
            ),
            "attr_fmt": ">5",
            "attr_ypos": 5,
            "attr_xpos": 50,
        },
    ),
    (
        ":",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 5,
            "attr_xpos": 55,
        },
    ),
    (
        "remote_addr",
        {
            "attr_func": None,
            "attr_color": "address",
            "color_func": lambda x: (
                "is_bgw_ip" if x.strip() in BGWS else "attr_color"
            ),
            "attr_fmt": "<15",
            "attr_ypos": 5,
            "attr_xpos": 56,
        },
    ),
    (
        "SSRC",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 6,
            "attr_xpos": 7,
        },
    ),
    (
        "local_ssrc_hex",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 6,
            "attr_xpos": 12,
        },
    ),
    (
        "Enc:",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 6,
            "attr_xpos": 25,
        },
    ),
    (
        "codec_enc",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "encrypted" if x.strip() != "Off" else "attr_color"
            ),
            "attr_fmt": "^22",
            "attr_ypos": 6,
            "attr_xpos": 29,
        },
    ),
    (
        "SSRC",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 6,
            "attr_xpos": 54,
        },
    ),
    (
        "remote_ssrc_hex",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 6,
            "attr_xpos": 59,
        },
    ),
    (
        "remote_ssrc_change",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "bold" if x and x != "(0)" else "attr_color"
            ),
            "attr_fmt": "",
            "attr_ypos": 6,
            "attr_xpos": 70,
        },
    ),
    (
        "RTP/RTCP",
        {
            "attr_func": None,
            "attr_color": "title",
            "color_func": None,
            "attr_fmt": "^36",
            "attr_ypos": 8,
            "attr_xpos": 1,
        },
    ),
    (
        "CODEC",
        {
            "attr_func": None,
            "attr_color": "title",
            "color_func": None,
            "attr_fmt": "^36",
            "attr_ypos": 8,
            "attr_xpos": 40,
        },
    ),
    (
        "RTP Packets (Rx/Tx):",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 9,
            "attr_xpos": 2,
        },
    ),
    (
        "rx_rtp_packets",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "attr_color" if x.strip().isdigit() and int(x.strip()) > 0
                else "anormal"
            ),
            "attr_fmt": ">7",
            "attr_ypos": 9,
            "attr_xpos": 22,
        },
    ),
    (
        "/",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 9,
            "attr_xpos": 30,
        },
    ),
    (
        "NA",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": ">5",
            "attr_ypos": 9,
            "attr_xpos": 32,
        },
    ),
    (
        "Psize/Ptime:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 9,
            "attr_xpos": 46,
        },
    ),
    (
        "codec_psize",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "attr_color" if x.strip() == "200B" else "anormal"
            ),
            "attr_fmt": ">4",
            "attr_ypos": 9,
            "attr_xpos": 61,
        },
    ),
    (
        "/",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 9,
            "attr_xpos": 65,
        },
    ),
    (
        "codec_ptime",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "attr_color" if x.strip() == "20mS" else "anormal"
            ),
            "attr_fmt": "",
            "attr_ypos": 9,
            "attr_xpos": 66,
        },
    ),
    (
        "RTCP Packets (Rx/Tx):",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 10,
            "attr_xpos": 1,
        },
    ),
    (
        "rx_rtp_rtcp",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "attr_color" if x and x.strip().isdigit() and
                             int(x.strip()) > 0
                else "anormal"
            ),
            "attr_fmt": ">7",
            "attr_ypos": 10,
            "attr_xpos": 22,
        },
    ),
    (
        "/",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 10,
            "attr_xpos": 30,
        },
    ),
    (
        "tx_rtp_rtcp",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">5",
            "attr_ypos": 10,
            "attr_xpos": 32,
        },
    ),
    (
        "Play-Time:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 10,
            "attr_xpos": 48,
        },
    ),
    (
        "codec_play_time",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 10,
            "attr_xpos": 60,
        },
    ),
    (
        "DSCP (Rx/Tx):",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 11,
            "attr_xpos": 9,
        },
    ),
    (
        "rx_rtp_dscp",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x and x != "46" else "attr_color"
            ),
            "attr_fmt": ">7",
            "attr_ypos": 11,
            "attr_xpos": 22,
        },
    ),
    (
        "/",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 11,
            "attr_xpos": 30,
        },
    ),
    (
        "tx_rtp_dscp",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x and x != "46" else "attr_color"
            ),
            "attr_fmt": ">5",
            "attr_ypos": 11,
            "attr_xpos": 32,
        },
    ),
    (
        "Avg-Loss:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 11,
            "attr_xpos": 49,
        },
    ),
    (
        "codec_avg_loss",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">6",
            "attr_ypos": 11,
            "attr_xpos": 59,
        },
    ),
    (
        "L2Pri (Rx/Tx):",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 12,
            "attr_xpos": 8,
        },
    ),
    (
        "rx_rtp_l2pri",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">7",
            "attr_ypos": 12,
            "attr_xpos": 22,
        },
    ),
    (
        "/",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 12,
            "attr_xpos": 30,
        },
    ),
    (
        "tx_rtp_l2pri",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">5",
            "attr_ypos": 12,
            "attr_xpos": 32,
        },
    ),
    (
        "Avg-RTT:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 12,
            "attr_xpos": 50,
        },
    ),
    (
        "codec_avg_rtt",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">7",
            "attr_ypos": 12,
            "attr_xpos": 58,
        },
    ),
    (
        "Duplicates (Rx):",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 13,
            "attr_xpos": 6,
        },
    ),
    (
        "rx_rtp_duplicates",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x and x != "0" else "attr_color"
            ),
            "attr_fmt": ">7",
            "attr_ypos": 13,
            "attr_xpos": 22,
        },
    ),
    (
        "Max-Jbuf-Delay:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 13,
            "attr_xpos": 43,
        },
    ),
    (
        "codec_max_jbuf_delay",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">7",
            "attr_ypos": 13,
            "attr_xpos": 58,
        },
    ),
    (
        "Seq-Fall (Rx):",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 14,
            "attr_xpos": 8,
        },
    ),
    (
        "rx_rtp_seqfall",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x and x != "0" else "attr_color"
            ),
            "attr_fmt": ">7",
            "attr_ypos": 14,
            "attr_xpos": 22,
        },
    ),
    (
        "JBuf-und/overruns:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 14,
            "attr_xpos": 40,
        },
    ),
    (
        "codec_jbuf_underruns",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">6",
            "attr_ypos": 14,
            "attr_xpos": 59,
        },
    ),
    (
        "/",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 14,
            "attr_xpos": 65,
        },
    ),
    (
        "codec_jbuf_overruns",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 14,
            "attr_xpos": 66,
        },
    ),
    (
        "LOCAL RTP STATISTICS",
        {
            "attr_func": None,
            "attr_color": "title",
            "color_func": None,
            "attr_fmt": "^36",
            "attr_ypos": 16,
            "attr_xpos": 1,
        },
    ),
    (
        "REMOTE RTP STATISTICS",
        {
            "attr_func": None,
            "attr_color": "title",
            "color_func": None,
            "attr_fmt": "^36",
            "attr_ypos": 16,
            "attr_xpos": 40,
        },
    ),
    (
        "Avg-Loss:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 17,
            "attr_xpos": 13,
        },
    ),
    (
        "rx_rtp_avg_loss",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">7",
            "attr_ypos": 17,
            "attr_xpos": 22,
        },
    ),
    (
        "Avg-Loss:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 17,
            "attr_xpos": 49,
        },
    ),
    (
        "rem_avg_loss",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">6",
            "attr_ypos": 17,
            "attr_xpos": 59,
        },
    ),
    (
        "Avg-Jitter:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 18,
            "attr_xpos": 11,
        },
    ),
    (
        "rx_rtp_avg_jitter",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">7",
            "attr_ypos": 18,
            "attr_xpos": 22,
        },
    ),
    (
        "Avg-Jitter:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 18,
            "attr_xpos": 47,
        },
    ),
    (
        "rem_avg_jitter",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">7",
            "attr_ypos": 18,
            "attr_xpos": 58,
        },
    ),
    (
        "Avg-RTT:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 19,
            "attr_xpos": 14,
        },
    ),
    (
        "rx_rtp_avg_rtt",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">7",
            "attr_ypos": 19,
            "attr_xpos": 22,
        },
    ),
]

COLORS = {
    "default": 0,
    "normal": 0,
    "dimmed": 64000,
    "anormal": 2560,
    "connected": 12288,
    "enabled": 12288,
    "odd": 41216,
    "even": 40192,
    "notg711": 53760,
    "is_bgw_ip": 31744,
    "line": 22528,
    "bold": 2097152,
    "standout": 65536,
    "status_on": 272896,
    "status_off": 262656,
    "title": 256,
    "address": 22016,
    "port": 58624,
    "codec": 0,
    "encrypted": 10752,
    "id": 13312,
}

ColumnDef = Tuple[str, Dict[str, Any]]
SpecItem = Tuple[str, Dict[str, Any]]
Cell = Tuple[int, int, str, int]

############################## END VARIABLES ##################################
############################## BEGIN CLASSES ##################################

class Layout(object):
    """A screen layout made of ordered column definitions.

    Each column is defined as a tuple: (column_name, attrs_dict).

    The attrs_dict typically contains:
        - "attr_name": str attribute name to read from the object
        - "attr_func": Optional[Callable[[Any], Any]] transform value
        - "attr_fmt": Optional[str] format spec (e.g. ">8", "<15")
        - "attr_xpos": int x-position for drawing
        - "attr_color": str default color name key
        - "color_func": Optional[Callable[[Any], str]] color selector
            Returns either:
              * a literal color name (e.g. "odd", "bold"), OR
              * the string "attr_color" to mean "use attrs_dict['attr_color']"
    """

    def __init__(
        self,
        columns: Iterable[ColumnDef],
        colors: Optional[Dict[str, int]] = None,
    ) -> None:
        """Initialize the Screen.

        Args:
            columns: Ordered iterable of (column_name, attrs_dict).
            colors: Mapping of color-name -> curses attribute (int).
                    If not provided, defaults to an empty dict and
                    you should pass a colors map to iter_cells().
        """
        self._columns = list(columns)
        self._by_name = {}
        self.colors = colors if colors is not None else {}

        for name, attrs in self._columns:
            if name in self._by_name:
                raise ValueError("Duplicate column name: {!r}".format(name))
            self._by_name[name] = attrs

    @property
    def columns(self) -> List[str]:
        """List of column names in display order."""
        return [name for name, _ in self._columns]

    @property
    def column_widths(self) -> List[int]:
        """List of computed widths for each column in display order."""
        return [self.column_width(name) for name in self.columns]

    def __contains__(self, name: str) -> bool:
        """Return True if a column exists by name."""
        return name in self._by_name

    def __getitem__(self, name: str) -> Dict[str, Any]:
        """Return the attrs dict for a given column name."""
        return self._by_name[name]

    def get(
        self,
        name: str,
        default: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return attrs dict for column name, or default if not found."""
        return self._by_name.get(name, default)

    def attr(self, name: str, key: str, default: Any = None) -> Any:
        """Return a single attribute from a column's attrs dict."""
        return self._by_name[name].get(key, default)

    def __iter__(self) -> Iterator[ColumnDef]:
        """Iterate (column_name, attrs_dict) in display order."""
        return iter(self._columns)

    def items(self) -> Iterator[ColumnDef]:
        """Alias for iterating column definitions."""
        return iter(self._columns)

    def column_width(self, name: str) -> int:
        """Compute column width from attr_fmt, else fall back to len(name).

        Extracts the first integer found in attr_fmt (e.g. ">14" -> 14).
        """
        fmt = self._by_name[name].get("attr_fmt")
        if not fmt:
            return len(name)

        m = re.search(r"(\d+)", str(fmt))
        return int(m.group(1)) if m else len(name)

    def iter_attrs(
        self,
        obj: Optional[Any] = None,
        *,
        row_y: int = 0,
        xoffset: int = 0,
        yoffset: int = 0,
        colors: Optional[Dict[str, int]] = COLORS,
        header: bool = False,
    ) -> Generator[Tuple[int, int, str, int], None, None]:
        """Yield (y, x, text, color) cells for this Screen"""
        cmap = colors if colors is not None else self.colors
        return iter_attrs(
            obj=obj,
            spec=self._columns,
            colors=cmap,
            xoffset=xoffset,
            yoffset=yoffset,
            default_y=row_y,
            header=header,
        )

############################## END CLASSES ####################################
############################## BEGIN FUNCTIONS ################################

def iter_attrs(
    obj: Optional[Any],
    spec: Iterable[SpecItem],
    colors: Dict[str, int],
    *,
    xoffset: int = 0,
    yoffset: int = 0,
    default_y: int = 0,
    header: bool = False,
) -> Generator[Cell, None, None]:
    """Render cells from a generic layout spec.

    Works for:
      - SCREENS-style specs (x only): provide default_y; omit attr_ypos
      - RTP_SCREEN-style specs (x+y): include attr_ypos in each item

    Spec dict keys supported:
      attr_name:     object attribute name (defaults to item name)
      attr_func:     callable(value) -> value
      attr_fmt:      format spec (e.g. '>8', '^36')
      attr_xpos:     x position
      attr_ypos:     y position (optional; falls back to default_y)
      attr_color:    default color name key (e.g. 'normal')
      color_func:    callable(value) -> str
                    returns either a literal color name OR 'attr_color'

    Args:
        obj: Object providing attributes; if None render labels.
        spec: Iterable of (name, attrs_dict) items.
        colors: Color name -> curses int attribute.
        xoffset/yoffset: Applied to coordinates.
        default_y: Used when attr_ypos is missing.
        header: If True, render item names (labels) instead of object values.

    Yields:
        (y, x, text, color_attr)
    """
    normal = int(colors.get("normal", 0))

    for name, d in spec:
        y = int(d.get("attr_ypos", default_y)) + yoffset
        x = int(d.get("attr_xpos", 0)) + xoffset

        # Value
        if header or obj is None:
            value = name
        else:
            attr_name = d.get("attr_name", name)
            value = getattr(obj, attr_name, name)

            fn = d.get("attr_func")
            if fn:
                try:
                    value = fn(value)
                except Exception:
                    pass

        # Color name
        cname = d.get("attr_color", "normal")
        cfn = d.get("color_func")
        
        if header or obj is None:
            cname = "normal"
        
        elif cfn:
            try:
                chosen = cfn(value)
                if chosen == "attr_color":
                    cname = d.get("attr_color", "normal")
                else:
                    cname = chosen
            except Exception:
                pass

        color_attr = int(colors.get(cname, normal))

        # Format
        fmt = d.get("attr_fmt")
        if fmt:
            try:
                ln = "".join(c for c in fmt if c.isdigit())
                if header or obj is None:
                    centered = "^" + ln if ln else "^" + str(len(value))
                    value = "{:{}}".format(value, centered)
                else:
                    ln = int(ln) if ln else None
                    value = "{:{}}".format(str(value)[:ln], fmt)
            except Exception:
                pass

        yield y, x, str(value), color_attr

############################## END FUNCTIONS ##################################

if __name__ == "__main__":
    import datetime
    from rtpparser import parse_rtpstat
    from queue import Queue
    from bgw import BGW
    from storage import MemoryStorage
    
    bgw = BGW(**{'bgw_ip': '10.10.48.58', 'proto': 'ptls', 'polling_secs': 10, 'bgw_name': 'AvayaG450A', 'bgw_number': '001', 'polls': 1, 'avg_poll_secs': 10, 'active_session_ids': set(), 'last_seen': datetime.datetime(2025, 12, 16, 14, 33, 39), 'last_session_id': '', 'show_announcements_files': '\r\n ID      File               Description    Size (Bytes)      Date\r\n---- ------------------ ------------------ ------------ -------------------\r\n101   moh.wav            announcement file      239798    2022-08-23,8:45:26  \r\n102   emergency.wav      announcement file       26618    2023-03-24,11:36:10 \r\n103   public_announceme  announcement file      201914    2024-10-24,7:37:52  \r\n104   mohtest.wav        announcement file     9648106    2025-07-15,14:50:16 \r\n\r\nNv-Ram:\r\nTotal bytes used             : 10119680  \r\nTotal bytes free             : 12672000  \r\nTotal bytes capacity (fixed) : 22791680', 'show_capture': '\r\n\r\nCapture service is enabled and active\r\nCapture start time 09/12/2025-09:25:13\r\nCapture stop time not-stopped\r\nCurrent buffer size is 1024 KB\r\nBuffer mode is non-cyclic\r\nMaximum number of bytes captured from each frame: 4096\r\nCapture list 501 on all interfaces\r\nCapture IPSec decrypted\r\nNumber of captured frames in file: 604 (out of 145200 total captured frames)\r\nMemory buffer occupancy: 4.62% (including overheads)', 'show_faults': '\r\n\r\nCURRENTLY ACTIVE FAULTS\r\n--------------------------------------------------------------------------\r\n\r\n-- Media Module Faults --\r\n\t+ Insertion failure, mmid = v5, 11/24-07:37:04.00\r\n\r\nCurrent Alarm Indications, ALM LED is off\r\n--------------------------------------------------------------------------\r\nNone', 'show_lldp_config': '\r\n\r\nLldp Configuration \r\n-------------------\r\nApplication status: disable \r\nTx interval: 30 seconds\r\nTx hold multiplier: 4 seconds\r\nTx delay: 2 seconds\r\nReinit delay: 2 seconds', 'show_mg_list': '\r\nSLOT   TYPE         CODE        SUFFIX  HW VINTAGE  FW VINTAGE \r\n----   --------     ----------  ------  ----------  -----------\r\nv1     -- Not Installed --\r\nv2     -- Not Installed --\r\nv3     E1T1         MM710       B       16          52\r\nv4     -- Not Installed --\r\nv5     -- Initializing --\r\nv6     Analog       MM714       B       23          94\r\nv7     -- Not Installed --\r\nv8     -- Not Installed --\r\nv10    Mainboard    G450        B       2           42.36.0(A)', 'show_port': '\r\nPort   Name             Status    Vlan Level  Neg     Dup. Spd. Type\r\n------ ---------------- --------- ---- ------ ------- ---- ---- ----------------\r\n10/5   NO NAME          connected 1     0     enable  full 1G   Avaya Inc., G450 Media Gateway 10/100/1000BaseTx Port 10/5\r\n\r\n10/6   NO NAME          no link   1     0     enable  full 1G   Avaya Inc., G450 Media Gateway 10/100/1000BaseTx Port 10/6', 'show_rtp_stat_summary': '', 'show_running_config': '\r\n\r\n! version 42.36.0\r\nConfig info release 42.36.0 time "13:33:51 16 DEC 2025 " serial_number 10IS41452851\r\n !\r\nencrypted-username +ikJzwEP/t+XkAlH3l+zsw== password G6uSyomIZMSDb0NnT4RwvSb4IrSGUtuQ9ypCGFikR4w= access-type fe/kaDE5GWBC9Nfj6bNkgA==\r\n!\r\nencrypted-username mJ6sF5BOZeIUWsyCb3C1bw== password 8tMk4PMmywAU0cVXzSERF/aaj9WF0EAq4dB4c0qOLbU= access-type gf0PKwZMZRJ4zRba06ZC3w==\r\nhostname "AvayaG450A"\r\nset system location "Calgary" \r\nno ip telnet \r\nip tftp-server file-system-size 2288\r\nset port mirror source-port 10/5 mirror-port 10/6 sampling always direction both\r\n!\r\nip capture-list 501\r\n name "udp"\r\n!\r\n ip-rule 1\r\n  ip-protocol udp\r\n exit\r\n ip-rule default\r\n  composite-operation "No-Capture"\r\n exit\r\n!\r\nexit\r\n!\r\nds-mode t1\r\n!\r\ninterface Vlan 1\r\n icc-vlan\r\n server-blade-vlan 5\r\n ip address 10.10.48.58     255.255.255.0  \r\n pmi\r\n exit\r\n!\r\ninterface FastEthernet 10/3\r\n exit\r\n!\r\ninterface FastEthernet 10/4\r\n exit\r\n!\r\ninterface Console\r\n speed 9600\r\n exit\r\n!\r\ninterface USB-Modem\r\n description "Default Modem Setup"\r\n timeout absolute 10\r\n ppp authentication ras\r\n no shutdown\r\n ip address 10.3.248.253    255.255.255.252\r\n exit\r\n!\r\ncapture max-frame-size 4096\r\ncapture buffer-mode non-cyclic\r\ncapture filter-group 501\r\nlogin authentication min-password-length 8\r\n!\r\nlogin authentication lockout 0 attempt 0\r\n! Avaya Login Confirmation Received.\r\nEASGManage enableEASG\r\nproduct-id 8c2ae2eead3e6cca800be892bb6e3411\r\n!\r\nset logging file enable \r\nset logging file condition all Error \r\nset logging file condition BOOT Debug \r\n!\r\nno snmp-server community \r\nencrypted-snmp-server user JSXE8Ccs0N0TnuoQek8jwLmaP391mjHjbt9glvbZ2M0= gAAa6QMAG08/c+A= v3ReadISO v3 auth sha 1FCIRMijXV+77fer97/S9O3FlfqIPrTOC5uTFcklYM8=  priv aes128 yyv5YmpCoEn5xZ24B7MR4Y03gnnqwygOY3eQTGRZZB0= \r\nencrypted-snmp-server user 0Ce9aP8Q25tEoXTe0YGwKmt2qLFQJ+UOpG6SMzseQdg= gAAa6QMAG08/c+A= v3TrapISO v3 auth sha TgX0mUpViHn56rSWounTurOYUdreS7rWWY7KssAnYj4=  priv aes128 p5Rdzsia/+4+Uc7f9oeJOj38gI6qX+2Fy1WDL5PTkh8= \r\nsnmp-server group v3ReadISO v3 priv read iso  \r\nsnmp-server group v3TrapISO v3 priv notify iso  \r\nsnmp-server host 10.10.48.92 traps v3 priv bbysnmpv3trap \r\n!\r\nip default-gateway 10.10.48.254    1 low  \r\n!\r\nset sync interface primary v3\r\nset sync source primary\r\nrtp-stat-service\r\nrtp-stat fault\r\nanalog-test\r\nexit\r\n!\r\nset sla-monitor enable\r\nset sla-server-ip-address 10.10.48.198\r\nudp keepalive 10\r\nset mgc list 10.10.48.240\r\nset mediaserver 10.10.48.240 10.10.48.240 23 telnet\r\nset mediaserver 10.10.48.240 10.10.48.240 5023 sat\r\n!#\r\n!# End of configuration file. Press Enter to continue.', 'show_sla_monitor': '\r\n\r\nSLA Monitor:                  Enabled\r\nRegistered Server IP Address: 0.0.0.0\r\nRegistered Server IP Port:    0\r\nConfigured Server IP Address: 10.10.48.198\r\nConfigured Server IP Port:    50011\r\nCapture Mode:                 None\r\nVersion:                      2.7.0', 'show_system': '\r\nSystem Name             : \r\nSystem Location         : Calgary\r\nSystem Contact          : \r\nUptime (d,h:m:s)        : 22,06:00:13\r\nCall Controller Time    : 13:33:56 16 DEC 2025 \r\nSerial No               : 13TG01116522\r\nModel                   : G450\r\nChassis HW Vintage      : 1\r\nChassis HW Suffix       : A\r\nMainboard HW Vintage    : 2\r\nMainboard HW Suffix     : B\r\nMainboard HW CS         : 2.1.7\r\nMainboard FW Vintage    : 42.36.0\r\nLAN MAC Address         : 00:1b:4f:3f:73:e0\r\nWAN1 MAC Address        : 00:1b:4f:3f:73:e1\r\nWAN2 MAC Address        : 00:1b:4f:3f:73:e2\r\nSERVICES MAC address    : 00:1b:4f:3f:73:e3\r\nMemory #1               : 256MB\r\nMemory #2               : Not present\r\nCompact Flash Memory    : No CompactFlash card is installed\r\nPSU #1                  : AC 400W\r\nPSU #2                  : Not present\r\nMedia Socket #1         : MP160 VoIP DSP Module\r\nMedia Socket #2         : Not present\r\nMedia Socket #3         : Not present\r\nMedia Socket #4         : Not present\r\nFAN Tray                : Present', 'show_temp': '\r\nAmbient\r\n-------\r\nTemperature : 36C (97F)\r\nHigh Warning: 42C (108F)\r\nLow Warning : -5C (23F)', 'show_utilization': '\r\n\r\nMod   CPU      CPU     RAM      RAM\r\n      5sec     60sec   used(%)  Total(Kb)\r\n---   ------   -----  -------  ----------\r\n10    Appl. Disabled    48%     190838 Kb', 'show_voip_dsp': '\r\nDSP #1 PARAMETERS\r\n--------------------------------------------------------------\r\nBoard type     : MP160\r\nHw Vintage     : 0 B\r\nFw Vintage     : 182\r\n\r\nDSP#1 CURRENT STATE\r\n--------------------------------------------------------------\r\nIn Use         : 0 of 160 channels, 0 of 4800 points (0.0% used)\r\nState          : Idle\r\nAdmin State    : Release\r\n\r\nCore# Channels Admin     State\r\n      In Use   State\r\n----- -------- --------- -------\r\n    1  0 of 40   Release Idle\r\n    2  0 of 40   Release Idle\r\n    3  0 of 40   Release Idle\r\n    4  0 of 40   Release Idle\r\n\r\n\r\nDSP #2 Not Present\r\n\r\n\r\nDSP #3 Not Present\r\n\r\n\r\nDSP #4 Not Present', 'queue': Queue(), '_active_session': None, '_announcements': None, '_capture_service': None, '_chassis_hw': None, '_comp_flash': None, '_cpu_util': None, '_dsp': None, '_faults': None, '_fw': None, '_hw': None, '_inuse_dsp': None, '_last_seen_time': None, '_lldp': None, '_location': None, '_mac': None, '_mainboard_hw': None, '_memory': None, '_mm_groupdict': None, '_mm_v1': None, '_mm_v2': None, '_mm_v3': None, '_mm_v4': None, '_mm_v5': None, '_mm_v6': None, '_mm_v7': None, '_mm_v8': None, '_mm_v10': None, '_model': None, '_port1': None, '_port1_status': None, '_port1_neg': None, '_port1_duplex': None, '_port1_speed': None, '_port2': None, '_port2_status': None, '_port2_neg': None, '_port2_duplex': None, '_port2_speed': None, '_port_redu': None, '_psu1': None, '_psu2': None, '_ram_util': None, '_rtp_stat_service': None, '_serial': None, '_slamon_service': None, '_sla_server': None, '_snmp': None, '_snmp_trap': None, '_temp': None, '_total_session': None, '_uptime': None})
    rtpdetails = parse_rtpstat("2024-11-04,10:06:07,001,00001", "\r\nshow rtp-stat detailed 00001\r\n\r\nSession-ID: 1\r\nStatus: Terminated, QOS: Ok, EngineId: 10\r\nStart-Time: 2024-11-04,10:06:07, End-Time: 2024-11-04,10:07:07\r\nDuration: 00:00:00\r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.110:2052 SSRC 1653399062\r\nRemote-Address: 10.10.48.192:35000 SSRC 2704961869 (0)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG711U 200B 20mS srtpAesCm128HmacSha180, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 4.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 0.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 1, Loss 0.3% #0, Avg-Loss 0.3%, RTT 0mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 0, Seq-Fall 0, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 46, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 0.0% #0, Avg-Loss 0.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n")

    for layout_name, columns in LAYOUTS.items():
        layout = Layout(columns)
        
        print(f"========== {layout_name} COLUMNS ==========")
        for y, x, text, color in layout.iter_attrs(obj=None):
            print(y, x, text, color)
    
        print(f"========== {layout_name} OBJ ==========")
        for y, x, text, color in layout.iter_attrs(obj=bgw):
            print(y, x, text, color)

    print("====== RTPDetailed ======")
    for y, x, text, color in iter_attrs(
        obj=rtpdetails,
        spec=RTP_LAYOUT,
        colors=COLORS,
        xoffset=0,
        yoffset=0,
    ):
        print(y, x, text, color)
