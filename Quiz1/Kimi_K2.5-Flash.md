 This is a classic DHCPv6-PD (Prefix Delegation) renewal issue with your ISP. Let me search for more information about this specific problem and potential solutions.  
 Based on your detailed description and my research, I can explain what's happening and provide better solutions.

## Root Cause Analysis

Your ISP's DHCPv6 server is **not properly handling renewals**. When `odhcp6c` tries to renew at T1 (typically 50% of preferred lifetime), the server returns:
- `No Binding` - The server lost/forgot your existing PD lease binding
- `Not On Link` - The server considers your prefix invalid for the link

According to the odhcp6c source code , when `odhcp6c` receives `NoBinding` during RENEW/REBIND, it **should** fall back to sending a REQUEST to re-establish the binding. However, your ISP appears to be assigning a **new** /64 prefix instead of renewing the existing one, causing the "old + new" prefix situation you observed.

This is a **server-side implementation issue** - the ISP's DHCPv6 server isn't properly maintaining lease state across renewals.

## Why Your Current Solution Is Imperfect

Your cron job using `SIGUSR1` (signal 16) forces a renew, which works because it triggers a fresh REQUEST transaction rather than a RENEW. However:

1. **Android clients cache addresses** - Android's IPv6 stack is aggressive about address retention for privacy reasons (RFC 8981 temporary addresses). They don't immediately drop old addresses when RAs stop including them.

2. **Timing mismatch** - Renewal failures happen based on T1/T2 timers, not clock time.

## Better Solutions

### Solution 1: Use `SIGUSR2` Instead (Recommended First Try)

`SIGUSR2` sends RELEASE + restarts with SOLICIT, which is cleaner than `SIGUSR1` for this scenario:

```bash
# Test this manually first
kill -SIGUSR2 $(pgrep odhcp6c)
```

However, this will cause a brief IPv6 outage. If your ISP consistently gives new prefixes, this won't solve the Android issue.

### Solution 2: Force Address Refresh on LAN (Better)

Create a script that forces RA reconfiguration on the LAN side when WAN6 renews:

```bash
#!/bin/sh
# /etc/hotplug.d/iface/99-ipv6-refresh

[ "$ACTION" = "ifupdate" ] && [ "$INTERFACE" = "wan6" ] && {
    # When WAN6 updates, force LAN to send RAs with 0-lifetime for old prefix
    # This tells clients to immediately deprecate old addresses
    
    logger -t ipv6-refresh "WAN6 updated, refreshing LAN IPv6"
    
    # Option A: Restart LAN interface (disruptive but effective)
    # /sbin/ifup lan
    
    # Option B: Force radvd/odhcpd to send immediate unsolicited RA
    # This requires odhcpd to be running
    killall -SIGUSR1 odhcpd 2>/dev/null
    
    # Option C: Shorten RA lifetime temporarily then restore
    uci set dhcp.lan.ra_lifetime='0'
    uci commit dhcp
    /etc/init.d/odhcpd restart
    sleep 5
    uci set dhcp.lan.ra_lifetime='1800'  # Restore default
    uci commit dhcp
    /etc/init.d/odhcpd restart
}
```

Make it executable:
```bash
chmod +x /etc/hotplug.d/iface/99-ipv6-refresh
```

### Solution 3: Shorten Valid Lifetimes (Best for Android)

The real fix is making old prefixes expire faster so Android abandons them:

**In LuCI:** Network → Interfaces → LAN → DHCP Server → IPv6 Settings

Or via UCI:

```bash
# Set very short preferred/valid lifetimes for delegated prefixes
uci set dhcp.lan.ra_lifetime='300'      # 5 minutes
uci set dhcp.lan.ra_mtu='1280'
uci set dhcp.lan.ra_hoplimit='64'

# More aggressive: set valid lifetime short
uci set dhcp.lan.ra_useleasetime='1'
uci set dhcp.lan.leasetime='10m'        # Short lease

uci commit dhcp
/etc/init.d/odhcpd restart
```

**Trade-off:** More frequent RS/RA traffic and address regeneration.

### Solution 4: Dynamic Prefix Update Script (Most Robust)

Create a script that monitors for prefix changes and forces client updates:

```bash
#!/bin/sh
# /usr/local/bin/ipv6-prefix-watchdog

OLD_PREFIX_FILE="/tmp/ipv6_old_prefix"

get_current_prefix() {
    ubus call network.interface.wan6 status | jsonfilter -e '@["ipv6-prefix"][0]["address"]'
}

force_client_refresh() {
    logger -t ipv6-watchdog "Prefix changed, forcing client refresh"
    
    # Method 1: Trigger unsolicited RA with short lifetimes
    echo 1 > /proc/sys/net/ipv6/conf/br-lan/forwarding  # Ensure forwarding
    echo 0 > /proc/sys/net/ipv6/conf/all/accept_ra      # Disable RA acceptance temporarily
    
    # Restart odhcpd to send new RAs
    /etc/init.d/odhcpd restart
    
    sleep 2
    
    # Restore
    echo 1 > /proc/sys/net/ipv6/conf/all/accept_ra
    
    # Method 2: If you have ndppd or similar, restart it
    # /etc/init.d/ndppd restart 2>/dev/null
    
    # Method 3: Clear neighbor cache to force rediscovery
    ip -6 neigh flush all
}

# Main loop
while true; do
    CURRENT=$(get_current_prefix)
    
    if [ -f "$OLD_PREFIX_FILE" ]; then
        OLD=$(cat "$OLD_PREFIX_FILE")
        if [ "$CURRENT" != "$OLD" ] && [ -n "$CURRENT" ]; then
            logger -t ipv6-watchdog "Prefix change detected: $OLD -> $CURRENT"
            force_client_refresh
        fi
    fi
    
    echo "$CURRENT" > "$OLD_PREFIX_FILE"
    sleep 60  # Check every minute
done
```

Run it:
```bash
chmod +x /usr/local/bin/ipv6-prefix-watchdog
# Add to /etc/rc.local to start on boot
echo "/usr/local/bin/ipv6-prefix-watchdog &" >> /etc/rc.local
```

### Solution 5: Workaround ISP Issue with odhcp6c Hacks

If your ISP consistently fails renewals, force `odhcp6c` to use REQUEST instead of RENEW by manipulating the client behavior:

```bash
# Edit /etc/config/network
uci set network.wan6.reqprefix='64'     # Request /64 specifically
uci set network.wan6.norelease='1'      # Don't send release on exit (keeps binding)
uci commit network
```

**Note:** `norelease` might help if the ISP's "No Binding" is caused by premature release processing.

### Solution 6: Android-Specific Mitigation

Since Android is the problematic client, you can try:

1. **Enable IPv6 privacy extensions on OpenWrt** (already default)
2. **Use shorter address lifetimes specifically:**
   ```bash
   uci set dhcp.lan.max_preferred_lifetime='300'
   uci set dhcp.lan.max_valid_lifetime='600'
   uci commit dhcp
   ```

3. **Force Android to use temporary addresses only** (client-side, not controllable from router)

## Recommended Approach

Given your constraints, I suggest **combining Solutions 2 and 3**:

1. **Set short RA lifetimes** (300s preferred, 600s valid) so old prefixes expire quickly
2. **Use the hotplug script** to force immediate RA updates when WAN6 changes
3. **Replace your cron job** with a smarter watchdog that triggers on actual prefix changes, not time

This minimizes Android's window of using stale addresses while being less disruptive than hourly interface restarts.

If the issue persists, **contact your ISP** - their DHCPv6 server is violating RFC 8415 by not maintaining bindings across renewals. The "No Binding" response to a valid RENEW is a server bug.