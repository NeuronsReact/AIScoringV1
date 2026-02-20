There is an IPv6-related problem between my local network and ISP
# `/etc/config/network` config
```
config interface 'lan'
        option device 'br-lan'
        option proto 'static'
        option ipaddr '192.168.12.1'
        option netmask '255.255.255.0'
        option ip6assign '64'
        list ip6class 'wan6'

config interface 'wan'
        option device 'wan'
        option proto 'dhcp'

config interface 'wan6'
        option device '@wan'
        option proto 'dhcpv6'
        option reqaddress 'try'
        option reqprefix 'auto'
        option norelease '1'
        option forceprefix '1'
        option noslaaconly '1'

config device
        option name 'wan'
        option mtu '1480'
        option ip6segmentrouting '1'
```

# Problem
My OpenWrt WAN6 is DHCPv6. ISP give /64 prefix size. 
I tried `ubus call network.interface.wan6 status`.
In normal status, the output is
 "ipv6-address": [
                {
                        "address": "<hidden for privacy>",
                        "mask": 128,
                        "preferred": 105255,
                        "valid": 191655
                }
        ],
        "ipv6-prefix": [
                {
                        "address": "<hidden for privacy>",
                        "mask": 64,
                        "preferred": 105255,
                        "valid": 191655,
                        "class": "wan6",
                        "assigned": {
                                "lan": {
                                        "address": "<hidden for privacy>",
                                        "mask": 64
                                }
                        }
                }
In abnormal status, the ouput is 
{
        "up": true,
        "pending": false,
        "available": true,
        "autostart": true,
        "dynamic": false,
        "uptime": 127329,
        "l3_device": "wan",
        "proto": "dhcpv6",
        "device": "wan",
        "metric": 0,
        "dns_metric": 0,
        "delegation": true,
        "ipv4-address": [

        ],
        "ipv6-address": [
                {
                        "address": "<old /128 address, hidden for privacy>",
                        "mask": 128,
                        "preferred": 66574,
                        "valid": 152974
                },
                {
                        "address": "<new /64 address, hidden for privacy>",
                        "mask": 64,
                        "preferred": 152991,
                        "valid": 239391
                }
        ],
        "ipv6-prefix": [
                {
                        "address": "<old /64 prefix, hidden for privacy>",
                        "mask": 64,
                        "preferred": 66574,
                        "valid": 152974,
                        "class": "wan6",
                        "assigned": {
                                "lan": {
                                        "address": "<old /64 prefix, hidden for privacy>",
                                        "mask": 64
                                }
                        }
                }
        ],
        "ipv6-prefix-assignment": [

        ],
        "route": [
                {
                        "target": "<new /64 prefix, hidden for privacy>",
                        "mask": 64,
                        "nexthop": "::",
                        "metric": 256,
                        "valid": 239391,
                        "source": "::/0"
                },
                {
                        "target": "::",
                        "mask": 0,
                        "nexthop": "fe80::1",
                        "metric": 512,
                        "valid": 1631,
                        "source": "<old /64 prefix, hidden for privacy>/64"
                },
                {
                        "target": "::",
                        "mask": 0,
                        "nexthop": "fe80::1",
                        "metric": 512,
                        "valid": 1631,
                        "source": "<new /64 address, hidden for privacy>/64"
                },
                {
                        "target": "::",
                        "mask": 0,
                        "nexthop": "fe80::1",
                        "metric": 512,
                        "valid": 1631,
                        "source": "<old /128 address, hidden for privacy>/128"
                }
        ],
        "dns-server": [
                "fe80::1",
                "fe80::1"
        ],
        "dns-search": [

        ],
        "neighbors": [

        ],
        "inactive": {
                "ipv4-address": [

                ],
                "ipv6-address": [

                ],
                "route": [

                ],
                "dns-server": [

                ],
                "dns-search": [

                ],
                "neighbors": [

                ]
        },
        "data": {
                "passthru": "000600160015001600170018001f003800400043005e005f006000170010fe80000000000000000000000000000100170010fe800000000000000000000000000001"
        }
}

At the same time, My OpenWrt router showed these log: 
```
Thu Feb 19 18:57:36 2026 daemon.warn odhcpd[1925]: No default route present, setting ra_lifetime to 0!
Thu Feb 19 23:29:40 2026 daemon.warn odhcp6c[29169]: Server returned IA_PD status 'No Binding '
Thu Feb 19 23:29:40 2026 daemon.warn odhcp6c[29169]: Server returned IA_PD status 'Not On Link '
Thu Feb 19 23:29:40 2026 daemon.warn odhcp6c[29169]: Server returned IA_PD status 'Not On Link '
Thu Feb 19 23:29:40 2026 daemon.warn odhcp6c[29169]: Server returned IA_PD status 'No Binding '
```
# Some solutions I tried
I tried a crontab command:
`0 * * * * kill -SIGUSR1 $(pgrep odhcp6c)`
It seems working for WAN6. WAN6 gets /128 IA_NA and /64 new prefix, and LAN also refreshes the PD (old prefix disappears, only the new one).
This solution is not perfect, because
1. Some downstream Android clients hold both old ipv6 addresses and new ones, and they keep using old ones. The old ones could only be removed by reconnecting to LAN, or by modifying an option of wan6 in LuCi (LuCi might restart something I guess). But, restarting LAN interface could not make Android devices abandon the old ipv6 addresses.
2. Renew failure won't accur in precisely 1:00, 2:00 and so on.