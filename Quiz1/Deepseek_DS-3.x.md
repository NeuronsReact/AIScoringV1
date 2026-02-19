We need to tackle two aspects of the problem: the unreliable DHCPv6 renewal that leaves stale prefixes, and the fact that Android clients cling to old IPv6 addresses long after the router has switched to a new prefix. Your hourly `SIGUSR1` to `odhcp6c` already forces a renewal, which usually obtains a fresh /64 prefix and removes the old one from the router’s perspective. However, Android devices keep using the old address because they have not received a Router Advertisement (RA) that explicitly deprecates it – they will only discard it after the original preferred lifetime (often days) expires.

The core issue is that OpenWrt’s RA daemon (`odhcpd`) stops advertising the old prefix once it’s gone from the LAN interface, but it does **not** send an RA with a zero lifetime for that prefix. Clients therefore retain the address until their local timers run out.

Below is a robust solution that automatically detects a prefix change and forces an immediate RA that deprecates the old prefix. It works alongside your existing cron job (or can replace it).

---

## Solution Overview

1. **Monitor the WAN6 prefix** every minute via `ubus`.
2. When the prefix changes, **add a temporary address** from the **old** prefix to the LAN interface with `preferred_lft 0` and `valid_lft 0`.
3. **Send `SIGUSR1` to `odhcpd`**, causing it to immediately send an RA that includes that prefix with zero lifetimes.
4. After a few seconds, remove the temporary address.
5. Store the new prefix for future comparisons.

This method does not require restarting services or modifying configuration files, and it works with the existing `odhcpd`.

---

## Step‑by‑Step Implementation

### 1. Create the monitoring script

Save the following as `/root/check_ipv6_prefix.sh` and make it executable (`chmod +x /root/check_ipv6_prefix.sh`).

```bash
#!/bin/sh

# File to store the last known WAN prefix
STATE_FILE="/tmp/last_wan_prefix"

# LAN interface (adjust if your LAN is not br-lan, e.g. eth0.1)
LAN_IF="br-lan"

# Get current WAN6 prefix from ubus
wan_status=$(ubus call network.interface.wan6 status 2>/dev/null)
if [ -z "$wan_status" ]; then
    logger -t ipv6-deprecate "Could not get WAN6 status"
    exit 1
fi

# Extract the first /64 prefix (assuming it's the delegated one)
current_prefix=$(echo "$wan_status" | jsonfilter -e '@["ipv6-prefix"][0].address')

# If no prefix found (e.g. IPv6 not working), exit
if [ -z "$current_prefix" ] || [ "$current_prefix" = "null" ]; then
    exit 0
fi

# Read previously stored prefix
if [ -f "$STATE_FILE" ]; then
    old_prefix=$(cat "$STATE_FILE")
else
    # First run: just store current prefix and exit
    echo "$current_prefix" > "$STATE_FILE"
    exit 0
fi

# Compare
if [ "$current_prefix" != "$old_prefix" ]; then
    logger -t ipv6-deprecate "WAN prefix changed from $old_prefix to $current_prefix"

    # Deprecate the old prefix on the LAN
    # Form an address from the old /64 (using ::1 as the interface identifier)
    old_addr="${old_prefix}1/64"

    # Add the address with zero lifetimes
    ip -6 addr add "$old_addr" dev "$LAN_IF" preferred_lft 0 valid_lft 0

    # Force odhcpd to send an RA immediately
    if pidof odhcpd > /dev/null; then
        kill -USR1 $(pidof odhcpd)
        logger -t ipv6-deprecate "Sent SIGUSR1 to odhcpd to advertise deprecated prefix"
    else
        logger -t ipv6-deprecate "odhcpd not running, skipping RA trigger"
    fi

    # Wait a moment for the RA to be sent
    sleep 5

    # Remove the temporary address
    ip -6 addr del "$old_addr" dev "$LAN_IF"

    # Store the new prefix
    echo "$current_prefix" > "$STATE_FILE"
fi
```

**Notes:**
- The script uses `jsonfilter` (part of `jshn`) to parse `ubus` output – this is standard on OpenWrt.
- The temporary address uses the suffix `::1`. This is arbitrary; any unique address from the old /64 works, as long as it doesn’t conflict with an existing address (the old prefix should no longer be on the interface).
- The `sleep 5` gives `odhcpd` enough time to send the RA. You can adjust it, but 5 seconds is safe.
- All actions are logged to the system log (view with `logread`).

### 2. Schedule the script to run every minute

Add the following line to root’s crontab (`crontab -e`):

```
* * * * * /root/check_ipv6_prefix.sh
```

If you prefer to keep your existing `SIGUSR1` cron job for `odhcp6c`, you may do so – it will complement this script by forcing renewals. However, the script above only reacts to prefix *changes*, not to expiring leases. You could merge both functions into one script (e.g., also trigger a renew if the remaining lifetime is low), but for simplicity you can keep both.

### 3. (Optional) Tune RA lifetimes

If you want to further reduce the time Android clients hold onto old addresses (as a fallback), you can shorten the default preferred/valid lifetimes advertised by `odhcpd`. Edit `/etc/config/dhcp` and add these options to your `lan` section:

```
config dhcp 'lan'
    option interface 'lan'
    option ra 'server'
    option dhcpv6 'server'
    option ra_preferred '1800'      # 30 minutes
    option ra_valid '3600'           # 1 hour
    # ... other options ...
```

Then restart `odhcpd` (`/etc/init.d/odhcpd restart`). This will cause clients to deprecate addresses sooner, but the script above already gives you **immediate** deprecation upon a prefix change.

---

## How It Works

- **When the WAN6 prefix changes** (e.g., after a renewal), the script detects the difference.
- It temporarily inserts an address from the **old** prefix on the LAN interface, with lifetimes set to zero.
- `odhcpd`, upon receiving `SIGUSR1`, sends an RA that includes that prefix with `preferred=0, valid=0`.
- Clients (including Android) receiving this RA will immediately deprecate and stop using any addresses from that prefix.
- The temporary address is then removed, leaving no trace.

This method is lightweight, does not disrupt existing connections, and ensures that old IPv6 addresses are cleaned up promptly.

---

## Troubleshooting

- **LAN interface name**: If your LAN interface is not `br-lan` (check with `ifstatus lan` or `ubus call network.interface.lan status`), adjust the `LAN_IF` variable in the script.
- **Multiple WAN prefixes**: The script assumes the first entry in `ipv6-prefix` is the one assigned to LAN. If your setup has more than one, you may need to refine the JSON path.
- **odhcpd not running**: If you use another RA daemon (e.g., `radvd`), you’ll need to adapt the signal part. For `radvd`, sending `SIGHUP` makes it re-read config and send RAs, but you would also need to temporarily add the deprecated prefix to its configuration – a more complex approach. The script above is tailored for OpenWrt’s default `odhcpd`.

---

## Why This Works Better

- **Immediate deprecation**: Clients get an RA with zero lifetimes, so they stop using the old address right away.
- **No service restarts**: The temporary address is added and removed cleanly, avoiding interruptions.
- **Minimal overhead**: Runs once per minute and only acts when a change actually occurs.

This should resolve the issue of Android clients holding onto stale IPv6 addresses after a prefix change, while your existing cron job keeps the WAN6 lease fresh.