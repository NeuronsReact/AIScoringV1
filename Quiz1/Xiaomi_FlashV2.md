Based on your detailed description, this is a common issue with some ISPs' DHCPv6 implementations, particularly when they use `/64` prefixes for both IA_NA and IA_PD. Here's a comprehensive solution:

## Understanding the Issue

The ISP is returning `No Binding` and `Not On Link` errors because:
1. The ISP's DHCPv6 server expects the IA_PD (prefix delegation) to match the IA_NA (address assignment)
2. Some ISPs incorrectly treat `/64` as both an address and a prefix
3. The server may be rejecting the renewal because it sees conflicting leases

## Better Solutions Than Hourly Restart

### 1. Configure OpenWrt to Use Only IA_NA (Recommended)

Since your ISP only provides a `/64` (which can't be delegated to LAN anyway), disable IA_PD and use only IA_NA:

```bash
# Edit /etc/config/network
config interface 'wan6'
    option proto 'dhcpv6'
    option reqaddress 'try'
    option reqprefix 'no'  # This disables IA_PD
    option clientid '1'
    option nobind '0'
```

Then restart network:
```bash
/etc/init.d/network restart
```

This will:
- Only request an address (IA_NA) from the ISP
- Avoid the IA_PD errors completely
- Still provide IPv6 connectivity to your LAN (via SLAAC or DHCPv6 on LAN side)

### 2. If You Need Prefix Delegation (Alternative Approach)

If you must have IA_PD, try this configuration:

```bash
config interface 'wan6'
    option proto 'dhcpv6'
    option reqaddress 'try'
    option reqprefix 'auto'
    option clientid '1'
    option nobind '0'
    option forceprefix '1'  # Force prefix even if server doesn't request it
    option norelease '1'    # Don't release on shutdown
```

### 3. LAN Side Configuration

For your LAN interface, since you're getting a `/64` from ISP:

```bash
config interface 'lan'
    option proto 'static'
    option ip6assign '64'  # This won't work with /64 from ISP
    # Instead, use SLAAC or manual configuration
```

Better approach for LAN:
- Use `option ip6assign '64'` but set it to a different prefix if possible
- Or configure LAN to use SLAAC only (no prefix delegation)

### 4. Script Alternative to Hourly Restart

Instead of killing odhcp6c every hour, create a more intelligent script:

```bash
#!/bin/sh
# /usr/bin/check-ipv6-renewal.sh

# Check if WAN6 interface has valid IPv6
if ! ubus call network.interface.wan6 status | grep -q '"ipv6-address":\[\]'; then
    # Only trigger if no IPv6 address
    kill -SIGUSR1 $(pgrep odhcp6c)
    logger "IPv6 renewal triggered due to missing address"
fi
```

Run this via cron every 15 minutes:
```bash
*/15 * * * * /usr/bin/check-ipv6-renewal.sh
```

### 5. DHCPv6 Client Options

Add these options to `/etc/config/dhcp`:

```bash
config dhcp 'wan6'
    option interface 'wan6'
    option dhcpv6 'client'
    option rapidcommit '0'
    option slaac '1'
```

### 6. For Android Device Issues

Since Android devices are stubborn with old addresses:

```bash
# In /etc/config/network for LAN interface
config interface 'lan'
    option proto 'static'
    # ... other settings
    option ip6assign '64'
    option ip6hint '1'  # Use a different hint to avoid conflicts
```

Or use DHCPv6 on LAN with shorter lifetimes:

```bash
# /etc/config/dhcp for LAN
config dhcp 'lan'
    option interface 'lan'
    option start '100'
    option limit '150'
    option leasetime '12h'
    option dhcpv6 'server'
    option ra 'server'
    option ra_slaac '1'
    option ra_useleasetime '1'
    option ra_advrouter '1'
    option ra_offlink '0'
    option ra_preference 'low'
    option ra_lifetime '1800'  # 30 minutes - shorter than default
```

## Recommended Action Plan

1. **First, try Solution #1** (disable IA_PD) - this should eliminate the errors completely
2. If you need prefix delegation, try Solution #2 with the modified configuration
3. Replace your hourly cron job with the smarter script from Solution #4
4. For Android devices, you might need to:
   - Temporarily disable Wi-Fi on Android and reconnect
   - Or enable "IPv6 privacy extensions" in Android developer options
   - Or use a static IPv6 on Android (not ideal but works)

## Debugging Commands

Check current status:
```bash
ubus call network.interface.wan6 status
```

Monitor DHCPv6 logs:
```bash
logread | grep odhcp6c
```

Check what the ISP is actually sending:
```bash
tcpdump -i wan6 -vvv port 546
```

The key is that a `/64` from ISP for both IA_NA and IA_PD is unusual and often problematic. Disabling IA_PD is usually the cleanest solution when the ISP provides only a `/64`.