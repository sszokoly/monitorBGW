#!/usr/bin/env python
# -*- encoding: utf-8 -*-

############################## BEGIN IMPORTS #################################

from typing import Any, Generator, Tuple, Dict

############################## END IMPORTS ###################################
############################## BEGIN VARIABLES ###############################

"""
SYSTEM
          1         2         3         4         5         6         7
01234567890123456789012345678901234567890123456789012345678901234567890123456789
+---+-------------+---------------+------------+-------------+-----+--+--------+
│BGW│    Name     |     LAN IP    │  LAN MAC   |   Uptime    |Model│HW│Firmware│
+---+-------------+---------------+------------+-------------+-----+--+--------+
|001|             |192.168.111.111|123456789ABC|153d05h23m06s| g430│1A│43.11.12│
+---+-------------+---------------+------------+-------------+-----+--+--------+

HW
          1         2         3         4         5         6         7
01234567890123456789012345678901234567890123456789012345678901234567890123456789
+---+----------+--------+------------+-----+----+------+---+----+-------+------+
│BGW│ Location |  Temp  |   Serial   |Chass|Main|Memory│DSP│Anno|C.Flash|Faults|
+---+----------+--------+------------+-----+----+------+---+----+-------+------+
|001|          |42C/108F|13TG01116522|   1A|  3A| 256MB│160│ 999|    1GB|     4|
+---+----------+--------+------------+-----+----+------+---+----+-------+------+

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
+---+----+---------+--------+---------+----+---------+--------+----+----+------+
|BGW|Port| Status  |  Neg.  |Spd.|Dup.|Port| Status  |  Neg.  |Spd.|Dup.|Redund|
+---+----+---------+--------+----+----+----+---------+--------+----+----+------+
|001|10/4|connected| enabled|100M|full|10/5|  no link| enabled|100M|half|   5/4|
+---+----+---------+--------+----+----+----+---------+--------+----+----+------+

SERVICE
          1         2         3         4         5         6         7
01234567890123456789012345678901234567890123456789012345678901234567890123456789
+---+--------+-----------------+----+--------+--------+---------------+--------+
|BGW|RTP-Stat| Capture-Service |SNMP|SNMPTrap| SLAMon | SLAMon Server |  LLDP  |
+---+--------+-----------------+----+--------+--------+---------------+--------+
|001|disabled| enabled/inactive|v2&3|disabled|disabled|101.101.111.198|disabled|
+---+--------+-----------------+----+--------+--------+---------------+--------+

STATUS
          1         2         3         4         5         6         7
01234567890123456789012345678901234567890123456789012345678901234567890123456789
+---+-----------+-----------+--------+----------+-----+-------+-------+--------+
|BGW|Act.Session|Tot.Session|InUseDSP|CPU 5s/60s| RAM |PollSec| Polls |LastSeen|
+---+-----------+-----------+--------+----------+-----+-------+-------+--------+
|001|        0/0| 32442/1443|     320| 100%/100%|  45%| 120.32|      3|11:02:11|
+---+-----------+-----------+--------+----------+-----+-------+-------+--------+

RTPSTAT
          1         2         3         4         5         6         7
01234567890123456789012345678901234567890123456789012345678901234567890123456789
+--------+--------+---+---------------+-----+---------------+-----+------+-----+
|  Start |   End  |BGW| Local-Address |LPort| Remote-Address|RPort| Codec| QoS | 
+--------+--------+---+---------------+-----+---------------+-----+------+-----+
|11:09:07|11:11:27|001|192.168.111.111|55555|100.100.100.100|55555| G711U|Fault|
+--------+--------+---+---------------+-----+---------------+-----+------+-----+
"""

SCREENS = {
    "SYSTEM": [
        ('BGW', {
            'attr_name': 'bgw_number',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>3',
            'attr_xpos': 1
        }),
        ('Name', {
            'attr_name': 'bgw_name',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>13',
            'attr_xpos': 5
        }),
        ('LAN IP', {
            'attr_name': 'host',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>15',
            'attr_xpos': 19
        }),
        ('LAN MAC', {
            'attr_name': 'mac',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>12',
            'attr_xpos': 35
        }),
        ('Uptime', {
            'attr_name': 'uptime',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>13',
            'attr_xpos': 48
        }),
        ('Model', {
            'attr_name': 'model',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>5',
            'attr_xpos': 62
        }),
        ('HW', {
            'attr_name': 'hw',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>2',
            'attr_xpos': 68
        }),
        ('Firmware', {
            'attr_name': 'fw',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>8',
            'attr_xpos': 71
        }),
    ],
    "HW": [
        ('BGW', {
            'attr_name': 'bgw_number',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>3',
            'attr_xpos': 1
        }),
        ('Location', {
            'attr_name': 'location',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>10',
            'attr_xpos': 5
        }),
        ('Temp', {
            'attr_name': 'temp',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>8',
            'attr_xpos': 16
        }),
        ('Serial', {
            'attr_name': 'serial',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>12',
            'attr_xpos': 25
        }),
        ('Chass', {
            'attr_name': 'chassis_hw',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>5',
            'attr_xpos': 38
        }),
        ('Main', {
            'attr_name': 'mainboard_hw',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>4',
            'attr_xpos': 44
        }),
        ('Memory', {
            'attr_name': 'memory',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>6',
            'attr_xpos': 49
        }),
        ('DSP', {
            'attr_name': 'dsp',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>3',
            'attr_xpos': 56
        }),
        ('Anno', {
            'attr_name': 'announcements',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>4',
            'attr_xpos': 60
        }),
        ('C.Flash', {
            'attr_name': 'comp_flash',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>7',
            'attr_xpos': 65
        }),
        ('Faults', {
            'attr_name': 'faults',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>6',
            'attr_xpos': 73
        }),
    ],
    "MODULE": [
        ('BGW', {
            'attr_name': 'bgw_number',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>3',
            'attr_xpos': 1
        }),
        ('v1', {
            'attr_name': 'mm_v1',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '<6',
            'attr_xpos': 5
        }),
        ('v2', {
            'attr_name': 'mm_v2',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '<6',
            'attr_xpos': 12
        }),
        ('v3', {
            'attr_name': 'mm_v3',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '<6',
            'attr_xpos': 19
        }),
        ('v4', {
            'attr_name': 'mm_v4',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '<6',
            'attr_xpos': 26
        }),
        ('v5', {
            'attr_name': 'mm_v5',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '<6',
            'attr_xpos': 33
        }),
        ('v6', {
            'attr_name': 'mm_v6',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '<6',
            'attr_xpos': 40
        }),
        ('v7', {
            'attr_name': 'mm_v7',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '<6',
            'attr_xpos': 47
        }),
        ('v8', {
            'attr_name': 'mm_v8',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '<6',
            'attr_xpos': 54
        }),
        ('v10 hw', {
            'attr_name': 'mm_v10',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>8',
            'attr_xpos': 61
        }),
        ('PSU1', {
            'attr_name': 'psu1',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>4',
            'attr_xpos': 70
        }),
        ('PSU2', {
            'attr_name': 'psu2',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>4',
            'attr_xpos': 75
        }),
    ],
    "PORT": [
        ('BGW', {
            'attr_name': 'bgw_number',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>3',
            'attr_xpos': 1
        }),
        ('Port', {
            'attr_name': 'port1',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>4',
            'attr_xpos': 5
        }),
        ('Status', {
            'attr_name': 'port1_status',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>9',
            'attr_xpos': 10
        }),
        ('Neg', {
            'attr_name': 'port1_neg',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>8',
            'attr_xpos': 20
        }),
        ('Spd.', {
            'attr_name': 'port1_speed',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>4',
            'attr_xpos': 29
        }),
        ('Dup.', {
            'attr_name': 'port1_duplex',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>4',
            'attr_xpos': 34
        }),
        ('Port', {
            'attr_name': 'port2',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>4',
            'attr_xpos': 39
        }),
        ('Status', {
            'attr_name': 'port2_status',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>9',
            'attr_xpos': 44
        }),
        ('Neg', {
            'attr_name': 'port2_neg',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>8',
            'attr_xpos': 54
        }),
        ('Spd.', {
            'attr_name': 'port2_speed',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>4',
            'attr_xpos': 63
        }),
        ('Dup.', {
            'attr_name': 'port2_duplex',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>4',
            'attr_xpos': 68
        }),
        ('Redund', {
            'attr_name': 'port_redu',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>6',
            'attr_xpos': 73
        }),
    ],
    "SERVICE": [
        ('BGW', {
            'attr_name': 'bgw_number',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>3',
            'attr_xpos': 1
        }),
        ('RTP-Stats', {
            'attr_name': 'rtp_stat_service',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>8',
            'attr_xpos': 5
        }),
        ('Capture-Service', {
            'attr_name': 'capture_service',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>17',
            'attr_xpos': 14
        }),
        ('SNMP', {
            'attr_name': 'snmp',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>4',
            'attr_xpos': 32
        }),
        ('SNMPTrap', {
            'attr_name': 'snmp_trap',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>8',
            'attr_xpos': 37
        }),
        ('SLAMon', {
            'attr_name': 'slamon_service',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>8',
            'attr_xpos': 46
        }),
        ('SLAMon Server', {
            'attr_name': 'sla_server',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>15',
            'attr_xpos': 55
        }),
        ('LLDP', {
            'attr_name': 'lldp',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>8',
            'attr_xpos': 71
        }),
    ],
    "STATUS": [
        ('BGW', {
            'attr_name': 'bgw_number',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>3',
            'attr_xpos': 1
        }),
        ('Act.Session', {
            'attr_name': 'active_session',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>11',
            'attr_xpos': 5
        }),
        ('Tot.Session', {
            'attr_name': 'total_session',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>11',
            'attr_xpos': 17
        }),
        ('InUseDSP', {
            'attr_name': 'inuse_dsp',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>8',
            'attr_xpos': 29
        }),
        ('CPU 5s/60s', {
            'attr_name': 'cpu_util',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>10',
            'attr_xpos': 38
        }),
        ('RAM', {
            'attr_name': 'ram_util',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>5',
            'attr_xpos': 49
        }),
        ('PollSec', {
            'attr_name': 'avg_poll_secs',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>7',
            'attr_xpos': 55
        }),
        ('Polls', {
            'attr_name': 'polls',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>7',
            'attr_xpos': 63
        }),
        ('LastSeen', {
            'attr_name': 'last_seen_time',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>8',
            'attr_xpos': 71
        }),
    ],
    "RTPSTAT": [
        ('Start', {
            'attr_name': 'start_time',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>8',
            'attr_xpos': 1
        }),
        ('End', {
            'attr_name': 'end_time',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>8',
            'attr_xpos': 10
        }),
        ('BGW', {
            'attr_name': 'bgw_number',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>3',
            'attr_xpos': 19
        }),
        ('Local-Address', {
            'attr_name': 'local_addr',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>15',
            'attr_xpos': 23
        }),
        ('LPort', {
            'attr_name': 'local_port',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>5',
            'attr_xpos': 39
        }),
        ('Remote-Address', {
            'attr_name': 'remote_addr',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>15',
            'attr_xpos': 45
        }),
        ('RPort', {
            'attr_name': 'remote_port',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>5',
            'attr_xpos': 61
        }),
        ('Codec', {
            'attr_name': 'codec',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>6',
            'attr_xpos': 67
        }),
        ('QoS', {
            'attr_name': 'qos',
            'attr_func': None,
            'attr_color': 'normal',
            'attr_color_alt': 'anormal',
            'color_func': lambda x: 'attr_color' if x else 'attr_color_alt',
            'attr_fmt': '>5',
            'attr_xpos': 74
        }),
    ]
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

RTP_SCREEN = [
    (
        "Session-ID:",
        {
            "attr_func": None,
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
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
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 1,
            "attr_xpos": 29,
        },
    ),
    (
        "QoS:",
        {
            "attr_func": None,
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 1,
            "attr_xpos": 48,
        },
    ),
    (
        "Samples:",
        {
            "attr_func": None,
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
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
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
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
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
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
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
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
            "attr_color_alt": "anormal",
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
            "attr_color_alt": "anormal",
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
            "attr_color": "address",
            "attr_color_alt": "anormal",
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
            "attr_color_alt": "anormal",
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
            "attr_color_alt": "anormal",
            "color_func": None,
            "attr_fmt": "<5",
            "attr_ypos": 5,
            "attr_xpos": 21,
        },
    ),
    (
        "<",
        {
            "attr_func": None,
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color_alt": "anormal",
            "color_func": None,
            "attr_fmt": "^7",
            "attr_ypos": 5,
            "attr_xpos": 35,
        },
    ),
    (
        ">",
        {
            "attr_func": None,
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color_alt": "anormal",
            "color_func": None,
            "attr_fmt": ">5",
            "attr_ypos": 5,
            "attr_xpos": 50,
        },
    ),
    (
        ":",
        {
            "attr_func": None,
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color_alt": "anormal",
            "color_func": None,
            "attr_fmt": "<15",
            "attr_ypos": 5,
            "attr_xpos": 56,
        },
    ),
    (
        "SSRC",
        {
            "attr_func": None,
            "attr_color": "normal",
            "attr_color_alt": "anormal",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 6,
            "attr_xpos": 7,
        },
    ),
    (
        "local_ssrc",
        {
            "attr_func": None,
            "attr_color": "standout",
            "attr_color_alt": "anormal",
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
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
            "color_func": None,
            "attr_fmt": "^22",
            "attr_ypos": 6,
            "attr_xpos": 29,
        },
    ),
    (
        "SSRC",
        {
            "attr_func": None,
            "attr_color": "normal",
            "attr_color_alt": "anormal",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 6,
            "attr_xpos": 54,
        },
    ),
    (
        "remote_ssrc",
        {
            "attr_func": None,
            "attr_color": "standout",
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
            "color_func": None,
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
            "attr_color_alt": "anormal",
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
            "attr_color_alt": "anormal",
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
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
            "color_func": None,
            "attr_fmt": ">7",
            "attr_ypos": 9,
            "attr_xpos": 22,
        },
    ),
    (
        "/",
        {
            "attr_func": None,
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "dimmmed",
            "attr_color_alt": "anormal",
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
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
            "color_func": None,
            "attr_fmt": ">3",
            "attr_ypos": 9,
            "attr_xpos": 62,
        },
    ),
    (
        "/",
        {
            "attr_func": None,
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 9,
            "attr_xpos": 66,
        },
    ),
    (
        "RTCP Packets (Rx/Tx):",
        {
            "attr_func": None,
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
            "color_func": None,
            "attr_fmt": ">7",
            "attr_ypos": 10,
            "attr_xpos": 22,
        },
    ),
    (
        "/",
        {
            "attr_func": None,
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
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
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
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
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
            "color_func": None,
            "attr_fmt": ">7",
            "attr_ypos": 11,
            "attr_xpos": 22,
        },
    ),
    (
        "/",
        {
            "attr_func": None,
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
            "color_func": None,
            "attr_fmt": ">5",
            "attr_ypos": 11,
            "attr_xpos": 32,
        },
    ),
    (
        "Avg-Loss:",
        {
            "attr_func": None,
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
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
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
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
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
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
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
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
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
            "color_func": None,
            "attr_fmt": ">7",
            "attr_ypos": 13,
            "attr_xpos": 22,
        },
    ),
    (
        "Max-Jbuf-Delay:",
        {
            "attr_func": None,
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
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
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
            "color_func": None,
            "attr_fmt": ">7",
            "attr_ypos": 14,
            "attr_xpos": 22,
        },
    ),
    (
        "JBuf-und/overruns:",
        {
            "attr_func": None,
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
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
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
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
            "attr_color_alt": "anormal",
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
            "attr_color_alt": "anormal",
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
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
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
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
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
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
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
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
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
            "attr_color": "normal",
            "attr_color_alt": "anormal",
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
            "attr_color": "standout",
            "attr_color_alt": "anormal",
            "color_func": None,
            "attr_fmt": ">7",
            "attr_ypos": 19,
            "attr_xpos": 22,
        },
    ),
]

COLORS = {
    'normal': 0,            # white
    'anormal': 0,
    'bold': 2097152,        # white bold
    'dim': 1048576,         # white dim
    'standout': 65536,      # white standout
    'status_on': 272896,    # green inverse
    'status_off': 262656    # red inverse
}

############################## END VARIABLES #################################
############################## BEGIN FUNCTIONS ###############################

def iter_screen(
    obj: Any,
    screen: str, 
    xoffset: int = 0,
    colors: Dict = COLORS
) -> Generator[Tuple[int, str, int], None, None]:
    """
    Generator yielding xpos, attr value and color.

    Args:
        obj: Object providing attributes referenced by SCREENS entries.
        screen: Screen name from SCREENS.
        xoffset: Offset added to attr_xpos.
        colors: Dictionary of color names and curses values

    Yields:
        (xpos, attr, color)
    """
    for _, d in SCREENS[screen]:

        if d.get("attr_func"):
            attr = d[d["attr_func"](getattr(obj, d["attr_name"], ""))]
        else:
            attr = getattr(obj, d["attr_name"], "")

        if d.get("color_func"):
            cname = d[d["color_func"](getattr(obj, d["attr_name"], "normal"))]
        else:
            cname = d["attr_color"]

        color = colors.get(cname, 0)

        if d.get("attr_fmt"):
            attr = "{:{}}".format(attr, d["attr_fmt"])

        yield d.get("attr_xpos", 0) + xoffset, str(attr), color

def iter_rtpdetailed(
    obj: Any,
    xoffset: int = 0,
    yoffset: int = 0,
) -> Generator[Tuple[int, int, str, int], None, None]:
    """
    Generator yielding RTP detailed view.

    Args:
        obj: RTPDetailed instance.
        xoffset: Offset added to attr_xpos.
        yoffset: Offset added to attr_ypos.

    Yields:
        Tuple[int, int, str, int]:
            (ypos, xpos, rendered_text, color)
    """
    for attr_name, d in RTP_SCREEN:

        ypos = d.get("attr_ypos", 0) + yoffset
        xpos = d.get("attr_xpos", 0) + xoffset

        if d.get("attr_func"):
            attr = d[d["attr_func"](getattr(obj, attr_name, attr_name))]
        else:
            attr = getattr(obj, attr_name, attr_name)

        if d.get("color_func"):
            cname = d[d["color_func"](getattr(obj, attr_name, "normal"))]
        else:
            cname = d["attr_color"]

        color = COLORS.get(cname, 0)

        if d.get("attr_fmt"):
            attr = "{:{}}".format(attr, d["attr_fmt"])

        yield ypos, xpos, str(attr), color

############################## END FUNCTIONS ###############################

if __name__ == "__main__":
    import datetime
    from rtpparser import parse_rtpstat
    from queue import Queue
    from bgw import BGW
    
    bgw = BGW(**{'bgw_ip': '10.10.48.58', 'proto': 'ptls', 'polling_secs': 10, 'bgw_name': 'AvayaG450A', 'bgw_number': '001', 'polls': 1, 'avg_poll_secs': 10, 'active_session_ids': set(), 'last_seen': datetime.datetime(2025, 12, 16, 14, 33, 39), 'last_session_id': '', 'show_announcements_files': '\r\n ID      File               Description    Size (Bytes)      Date\r\n---- ------------------ ------------------ ------------ -------------------\r\n101   moh.wav            announcement file      239798    2022-08-23,8:45:26  \r\n102   emergency.wav      announcement file       26618    2023-03-24,11:36:10 \r\n103   public_announceme  announcement file      201914    2024-10-24,7:37:52  \r\n104   mohtest.wav        announcement file     9648106    2025-07-15,14:50:16 \r\n\r\nNv-Ram:\r\nTotal bytes used             : 10119680  \r\nTotal bytes free             : 12672000  \r\nTotal bytes capacity (fixed) : 22791680', 'show_capture': '\r\n\r\nCapture service is enabled and active\r\nCapture start time 09/12/2025-09:25:13\r\nCapture stop time not-stopped\r\nCurrent buffer size is 1024 KB\r\nBuffer mode is non-cyclic\r\nMaximum number of bytes captured from each frame: 4096\r\nCapture list 501 on all interfaces\r\nCapture IPSec decrypted\r\nNumber of captured frames in file: 604 (out of 145200 total captured frames)\r\nMemory buffer occupancy: 4.62% (including overheads)', 'show_faults': '\r\n\r\nCURRENTLY ACTIVE FAULTS\r\n--------------------------------------------------------------------------\r\n\r\n-- Media Module Faults --\r\n\t+ Insertion failure, mmid = v5, 11/24-07:37:04.00\r\n\r\nCurrent Alarm Indications, ALM LED is off\r\n--------------------------------------------------------------------------\r\nNone', 'show_lldp_config': '\r\n\r\nLldp Configuration \r\n-------------------\r\nApplication status: disable \r\nTx interval: 30 seconds\r\nTx hold multiplier: 4 seconds\r\nTx delay: 2 seconds\r\nReinit delay: 2 seconds', 'show_mg_list': '\r\nSLOT   TYPE         CODE        SUFFIX  HW VINTAGE  FW VINTAGE \r\n----   --------     ----------  ------  ----------  -----------\r\nv1     -- Not Installed --\r\nv2     -- Not Installed --\r\nv3     E1T1         MM710       B       16          52\r\nv4     -- Not Installed --\r\nv5     -- Initializing --\r\nv6     Analog       MM714       B       23          94\r\nv7     -- Not Installed --\r\nv8     -- Not Installed --\r\nv10    Mainboard    G450        B       2           42.36.0(A)', 'show_port': '\r\nPort   Name             Status    Vlan Level  Neg     Dup. Spd. Type\r\n------ ---------------- --------- ---- ------ ------- ---- ---- ----------------\r\n10/5   NO NAME          connected 1     0     enable  full 1G   Avaya Inc., G450 Media Gateway 10/100/1000BaseTx Port 10/5\r\n\r\n10/6   NO NAME          no link   1     0     enable  full 1G   Avaya Inc., G450 Media Gateway 10/100/1000BaseTx Port 10/6', 'show_rtp_stat_summary': '', 'show_running_config': '\r\n\r\n! version 42.36.0\r\nConfig info release 42.36.0 time "13:33:51 16 DEC 2025 " serial_number 10IS41452851\r\n !\r\nencrypted-username +ikJzwEP/t+XkAlH3l+zsw== password G6uSyomIZMSDb0NnT4RwvSb4IrSGUtuQ9ypCGFikR4w= access-type fe/kaDE5GWBC9Nfj6bNkgA==\r\n!\r\nencrypted-username mJ6sF5BOZeIUWsyCb3C1bw== password 8tMk4PMmywAU0cVXzSERF/aaj9WF0EAq4dB4c0qOLbU= access-type gf0PKwZMZRJ4zRba06ZC3w==\r\nhostname "AvayaG450A"\r\nset system location "Calgary" \r\nno ip telnet \r\nip tftp-server file-system-size 2288\r\nset port mirror source-port 10/5 mirror-port 10/6 sampling always direction both\r\n!\r\nip capture-list 501\r\n name "udp"\r\n!\r\n ip-rule 1\r\n  ip-protocol udp\r\n exit\r\n ip-rule default\r\n  composite-operation "No-Capture"\r\n exit\r\n!\r\nexit\r\n!\r\nds-mode t1\r\n!\r\ninterface Vlan 1\r\n icc-vlan\r\n server-blade-vlan 5\r\n ip address 10.10.48.58     255.255.255.0  \r\n pmi\r\n exit\r\n!\r\ninterface FastEthernet 10/3\r\n exit\r\n!\r\ninterface FastEthernet 10/4\r\n exit\r\n!\r\ninterface Console\r\n speed 9600\r\n exit\r\n!\r\ninterface USB-Modem\r\n description "Default Modem Setup"\r\n timeout absolute 10\r\n ppp authentication ras\r\n no shutdown\r\n ip address 10.3.248.253    255.255.255.252\r\n exit\r\n!\r\ncapture max-frame-size 4096\r\ncapture buffer-mode non-cyclic\r\ncapture filter-group 501\r\nlogin authentication min-password-length 8\r\n!\r\nlogin authentication lockout 0 attempt 0\r\n! Avaya Login Confirmation Received.\r\nEASGManage enableEASG\r\nproduct-id 8c2ae2eead3e6cca800be892bb6e3411\r\n!\r\nset logging file enable \r\nset logging file condition all Error \r\nset logging file condition BOOT Debug \r\n!\r\nno snmp-server community \r\nencrypted-snmp-server user JSXE8Ccs0N0TnuoQek8jwLmaP391mjHjbt9glvbZ2M0= gAAa6QMAG08/c+A= v3ReadISO v3 auth sha 1FCIRMijXV+77fer97/S9O3FlfqIPrTOC5uTFcklYM8=  priv aes128 yyv5YmpCoEn5xZ24B7MR4Y03gnnqwygOY3eQTGRZZB0= \r\nencrypted-snmp-server user 0Ce9aP8Q25tEoXTe0YGwKmt2qLFQJ+UOpG6SMzseQdg= gAAa6QMAG08/c+A= v3TrapISO v3 auth sha TgX0mUpViHn56rSWounTurOYUdreS7rWWY7KssAnYj4=  priv aes128 p5Rdzsia/+4+Uc7f9oeJOj38gI6qX+2Fy1WDL5PTkh8= \r\nsnmp-server group v3ReadISO v3 priv read iso  \r\nsnmp-server group v3TrapISO v3 priv notify iso  \r\nsnmp-server host 10.10.48.92 traps v3 priv bbysnmpv3trap \r\n!\r\nip default-gateway 10.10.48.254    1 low  \r\n!\r\nset sync interface primary v3\r\nset sync source primary\r\nrtp-stat-service\r\nrtp-stat fault\r\nanalog-test\r\nexit\r\n!\r\nset sla-monitor enable\r\nset sla-server-ip-address 10.10.48.198\r\nudp keepalive 10\r\nset mgc list 10.10.48.240\r\nset mediaserver 10.10.48.240 10.10.48.240 23 telnet\r\nset mediaserver 10.10.48.240 10.10.48.240 5023 sat\r\n!#\r\n!# End of configuration file. Press Enter to continue.', 'show_sla_monitor': '\r\n\r\nSLA Monitor:                  Enabled\r\nRegistered Server IP Address: 0.0.0.0\r\nRegistered Server IP Port:    0\r\nConfigured Server IP Address: 10.10.48.198\r\nConfigured Server IP Port:    50011\r\nCapture Mode:                 None\r\nVersion:                      2.7.0', 'show_system': '\r\nSystem Name             : \r\nSystem Location         : Calgary\r\nSystem Contact          : \r\nUptime (d,h:m:s)        : 22,06:00:13\r\nCall Controller Time    : 13:33:56 16 DEC 2025 \r\nSerial No               : 13TG01116522\r\nModel                   : G450\r\nChassis HW Vintage      : 1\r\nChassis HW Suffix       : A\r\nMainboard HW Vintage    : 2\r\nMainboard HW Suffix     : B\r\nMainboard HW CS         : 2.1.7\r\nMainboard FW Vintage    : 42.36.0\r\nLAN MAC Address         : 00:1b:4f:3f:73:e0\r\nWAN1 MAC Address        : 00:1b:4f:3f:73:e1\r\nWAN2 MAC Address        : 00:1b:4f:3f:73:e2\r\nSERVICES MAC address    : 00:1b:4f:3f:73:e3\r\nMemory #1               : 256MB\r\nMemory #2               : Not present\r\nCompact Flash Memory    : No CompactFlash card is installed\r\nPSU #1                  : AC 400W\r\nPSU #2                  : Not present\r\nMedia Socket #1         : MP160 VoIP DSP Module\r\nMedia Socket #2         : Not present\r\nMedia Socket #3         : Not present\r\nMedia Socket #4         : Not present\r\nFAN Tray                : Present', 'show_temp': '\r\nAmbient\r\n-------\r\nTemperature : 36C (97F)\r\nHigh Warning: 42C (108F)\r\nLow Warning : -5C (23F)', 'show_utilization': '\r\n\r\nMod   CPU      CPU     RAM      RAM\r\n      5sec     60sec   used(%)  Total(Kb)\r\n---   ------   -----  -------  ----------\r\n10    Appl. Disabled    48%     190838 Kb', 'show_voip_dsp': '\r\nDSP #1 PARAMETERS\r\n--------------------------------------------------------------\r\nBoard type     : MP160\r\nHw Vintage     : 0 B\r\nFw Vintage     : 182\r\n\r\nDSP#1 CURRENT STATE\r\n--------------------------------------------------------------\r\nIn Use         : 0 of 160 channels, 0 of 4800 points (0.0% used)\r\nState          : Idle\r\nAdmin State    : Release\r\n\r\nCore# Channels Admin     State\r\n      In Use   State\r\n----- -------- --------- -------\r\n    1  0 of 40   Release Idle\r\n    2  0 of 40   Release Idle\r\n    3  0 of 40   Release Idle\r\n    4  0 of 40   Release Idle\r\n\r\n\r\nDSP #2 Not Present\r\n\r\n\r\nDSP #3 Not Present\r\n\r\n\r\nDSP #4 Not Present', 'queue': Queue(), '_active_session': None, '_announcements': None, '_capture_service': None, '_chassis_hw': None, '_comp_flash': None, '_cpu_util': None, '_dsp': None, '_faults': None, '_fw': None, '_hw': None, '_inuse_dsp': None, '_last_seen_time': None, '_lldp': None, '_location': None, '_mac': None, '_mainboard_hw': None, '_memory': None, '_mm_groupdict': None, '_mm_v1': None, '_mm_v2': None, '_mm_v3': None, '_mm_v4': None, '_mm_v5': None, '_mm_v6': None, '_mm_v7': None, '_mm_v8': None, '_mm_v10': None, '_model': None, '_port1': None, '_port1_status': None, '_port1_neg': None, '_port1_duplex': None, '_port1_speed': None, '_port2': None, '_port2_status': None, '_port2_neg': None, '_port2_duplex': None, '_port2_speed': None, '_port_redu': None, '_psu1': None, '_psu2': None, '_ram_util': None, '_rtp_stat_service': None, '_serial': None, '_slamon_service': None, '_sla_server': None, '_snmp': None, '_snmp_trap': None, '_temp': None, '_total_session': None, '_uptime': None})
    rtpdetailed =  parse_rtpstat("2024-11-04,10:06:07,001,00001", "\r\nshow rtp-stat detailed 00001\r\n\r\nSession-ID: 1\r\nStatus: Terminated, QOS: Ok, EngineId: 10\r\nStart-Time: 2024-11-04,10:06:07, End-Time: 2024-11-04,10:07:07\r\nDuration: 00:00:00\r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.110:2052 SSRC 1653399062\r\nRemote-Address: 10.10.48.192:35000 SSRC 2704961869 (0)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG711U 200B 20mS srtpAesCm128HmacSha180, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 4.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 0.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 1, Loss 0.3% #0, Avg-Loss 0.3%, RTT 0mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 0, Seq-Fall 0, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 46, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 0.0% #0, Avg-Loss 0.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n")

    print("========== BGW ==========")
    for item in iter_screen(bgw, "SYSTEM"):
        print(item)

    print("====== RTPDetailed ======")
    for item in iter_rtpdetailed(rtpdetailed):
        print(item)
