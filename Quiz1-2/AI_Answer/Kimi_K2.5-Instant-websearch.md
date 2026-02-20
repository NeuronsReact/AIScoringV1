 I'll help you analyze this IPv6 DHCPv6-PD issue. This is a complex problem involving prefix delegation renewal failures and client address lingering. Let me search for relevant information about these specific odhcp6c/odhcpd behaviors and solutions.  
 Based on my analysis of your configuration and the search results, I can explain what's happening and provide better solutions.

## Root Cause Analysis

Your ISP is returning `No Binding` and `Not On Link` errors during DHCPv6-PD renewal. According to the [odhcp6c source code](https://github.com/openwrt/odhcp6c/blob/master/src/dhcpv6.c), when these status codes are received during RENEW/REBIND, odhcp6c transitions to REQUEST state to re-acquire the lease . However, your ISP seems to be assigning **new prefixes** instead of extending the existing binding, causing the "old + new" address accumulation you see.

The `No default route present, setting ra_lifetime to 0!` warning occurs because during the transition period, odhcpd detects that the old prefix is deprecated but the new one isn't fully active yet, temporarily breaking default route advertisement to LAN clients .

## Why Your SIGUSR1 Cronjob Is Imperfect

1. **SIGUSR1 only triggers a RENEW** - it doesn't clear stale state 
2. **Android clients cache addresses** - they don't respond to RAs with zero-lifetime for deprecated prefixes unless the interface cycles
3. **Timing mismatch** - renewals happen at T1/T2 intervals (typically hours), not on the hour

## Better Solutions

### Solution 1: Force Full Restart (More Aggressive)

Replace your cronjob with this script that fully restarts the interface:

```bash
#!/bin/sh
# /usr/local/bin/ipv6-fix.sh
# Detect if we have stale addresses (multiple /64s or old /128 with new /64)

. /lib/functions/network.sh

network_get_device device wan6
network_get_ipaddrs6 addrs wan6

# Count /64 addresses on WAN interface
count_64=$(echo "$addrs" | grep -c '/64' 2>/dev/null)

if [ "$count_64" -gt 1 ] 2>/dev/null || [ -f /tmp/ipv6_stale_flag ]; then
    logger -t ipv6-fix "Stale addresses detected, restarting wan6"
    # SIGUSR2 sends RELEASE then SOLICIT (cleaner than SIGUSR1)
    killall -SIGUSR2 odhcp6c 2>/dev/null
    sleep 2
    # Force interface bounce if needed
    ifdown wan6
    sleep 1
    ifup wan6
    rm -f /tmp/ipv6_stale_flag
fi
```

Crontab (every 10 minutes):
```cron
*/10 * * * * /usr/local/bin/ipv6-fix.sh
```

### Solution 2: Trigger on DHCP Events (Event-Driven)

Create a hotplug script that reacts to odhcp6c failures:

```bash
#!/bin/sh
# /etc/hotplug.d/iface/99-ipv6-fix

[ "$ACTION" = "ifupdate" ] && [ "$INTERFACE" = "wan6" ] || exit 0

# Check for error conditions in log
if logread | tail -5 | grep -q "No Binding\|Not On Link"; then
    logger -t ipv6-hotplug "PD binding failure detected, scheduling restart"
    # Schedule restart to allow current operation to complete
    (sleep 10; ifdown wan6; sleep 2; ifup wan6) &
fi
```

### Solution 3: Fix Android Stale Addresses (Client-Side)

Android's address retention is the harder problem. The nuclear option is to bounce the LAN interface when WAN6 renews:

```bash
#!/bin/sh
# Add to /etc/hotplug.d/iface/98-lan-bounce

[ "$ACTION" = "ifupdate" ] && [ "$INTERFACE" = "wan6" ] || exit 0

# Only bounce if prefix actually changed
old_prefix=$(cat /tmp/last_ipv6_prefix 2>/dev/null)
new_prefix=$(ubus call network.interface.wan6 status | jsonfilter -e '@["ipv6-prefix"][0].address' 2>/dev/null)

if [ -n "$old_prefix" ] && [ "$old_prefix" != "$new_prefix" ]; then
    logger -t ipv6-fix "Prefix changed ($old_prefix -> $new_prefix), bouncing LAN"
    ifdown lan
    sleep 2
    ifup lan
fi

echo "$new_prefix" > /tmp/last_ipv6_prefix
```

**Warning:** This disconnects all LAN clients briefly but forces Android to drop stale addresses.

### Solution 4: ISP Workaround Configuration

Try adding these options to your `wan6` config to handle broken ISP behavior:

```bash
uci set network.wan6.noserverunicast='1'  # Ignore unicast, use multicast 
uci set network.wan6.strict_rfc7550='0'   # Be lenient with non-compliant servers
uci set network.wan6.soltimeout='120'     # Longer solicit timeout
uci commit network
```

### Solution 5: Reduce Preferred Lifetime (If ISP Supports It)

Some ISPs allow you to request shorter lifetimes, causing faster stale address cleanup:

```bash
uci set network.wan6.reqpreflifetime='300'  # Request 5min preferred, forces faster Android refresh
uci commit network
```

## Recommended Approach

Combine **Solution 2** (event-driven detection) with **Solution 3** (LAN bounce on prefix change). This is cleaner than cron because it reacts to actual failures rather than polling.

Also check if your ISP supports **Rapid Commit** (faster recovery):
```bash
uci set network.wan6.rapidcommit='1'
uci commit network
```

If the ISP consistently gives new prefixes on every renewal (rather than extending), this is technically non-compliant behavior, and you may need to script around it as shown above.