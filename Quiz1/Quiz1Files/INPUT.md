There is an IPv6-related problem between my local network and ISP
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
I haven't try this command in abnormal situation, but in those abnormal situation, there is a refreshed /128 IA_NA, a refreshed /64 IA_NA (which should be the prefix), and an old /64 prefix (not a valid prefix since). At the same time, My OpenWrt router showed these log: 
```
Tue Feb 17 20:42:52 2026 daemon.warn odhcp6c[8542]: Server returned IA_PD status 'No Binding '
Tue Feb 17 20:42:52 2026 daemon.warn odhcp6c[8542]: Server returned IA_PD status 'Not On Link '
Tue Feb 17 20:42:52 2026 daemon.warn odhcp6c[8542]: Server returned IA_PD status 'Not On Link '
Tue Feb 17 20:42:52 2026 daemon.warn odhcp6c[8542]: Server returned IA_PD status 'No Binding '
```
# Some solutions I tried
I tried a crontab command:
`0 * * * * kill -SIGUSR1 $(pgrep odhcp6c)`
It seems working for WAN6. WAN6 gets /128 IA_NA and /64 new prefix, and LAN also refreshes the PD (old prefix disappears, only the new one).
This solution is not perfect, because
1. Some downstream Android clients hold both old ipv6 addresses and new ones, and they keep using old ones. The old ones could only be removed by reconnecting to LAN, or by modifying an option of wan6 in LuCi (LuCi might restart something I guess). But, restarting LAN interface could not make Android devices abandon the old ipv6 addresses.
2. Renew failure won't accur in precisely 1:00, 2:00 and so on.