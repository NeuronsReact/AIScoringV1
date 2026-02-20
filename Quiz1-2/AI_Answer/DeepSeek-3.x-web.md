Your IPv6 issue stems from a DHCPv6-PD renewal failure that leaves a stale /64 prefix assigned to your LAN. This causes Android clients to retain old addresses long after a new prefix is obtained, leading to connectivity problems. Below is an analysis of the root cause and several solutions, ranging from simple configuration tweaks to automated cleanup scripts.

## 1. Understanding the Problem

From your logs and status output:

- **odhcp6c errors**: `Server returned IA_PD status 'No Binding'` and `'Not On Link'` indicate the ISP’s DHCPv6 server does not recognize the existing prefix binding or considers it invalid. This typically happens when the server’s lease state is lost or the client’s IAID/DUID changes.
- **Dual addresses on WAN6**: After failure, you see both an old /128 IA_NA address and a new /64 address (likely from SLAAC on the WAN interface). The old /64 prefix remains assigned to LAN, while the new one is not delegated.
- **Stale prefixes on LAN**: The old prefix continues to be advertised by odhcpd, and clients (especially Android) keep using addresses from it due to long preferred/valid lifetimes (up to 42 hours).

Your cron job sending `SIGUSR1` to odhcp6c forces a renew, obtaining a new prefix but does **not** release the old one (`norelease 1`). The old prefix therefore lingers until its lifetime expires, and clients are not informed to deprecate it.

## 2. Immediate Configuration Adjustments

Start by modifying your `wan6` interface settings to align with typical ISP expectations and improve renewal behavior.

```uci
uci set network.wan6.forceprefix='0'       # Do not request a new prefix if one is already assigned
uci set network.wan6.norelease='0'          # Send release on exit (helps clean up old leases)
uci commit network
/etc/init.d/network restart
```

- **`forceprefix 0`** (default) tells odhcp6c to only request a prefix when none is assigned, and otherwise just renew the existing one. This avoids confusing the server with duplicate requests.
- **`norelease 0`** ensures that when odhcp6c exits (e.g., during a restart), it sends a RELEASE message, allowing the server to free the binding.

If the ISP uses IA_NA for address assignment and IA_PD separately, ensure `reqaddress try` and `reqprefix auto` are sufficient. Some ISPs require a specific prefix length; you could try `reqprefix 64` instead of `auto`.

## 3. Stabilizing DHCPv6 Renewals

If the problem persists, the ISP’s server may be buggy or your DUID/IAID might be unstable. Add explicit identifiers:

```sh
# Generate a stable DUID (if not already present)
cat > /etc/duid <<EOF
00010001$(dd if=/dev/urandom bs=8 count=1 2>/dev/null | hexdump -e '8/1 "%02x"')
EOF

uci set network.wan6.duid=$(cat /etc/duid)   # Use the generated DUID
uci set network.wan6.iaid='1'                 # Arbitrary but consistent IAID
uci commit network
```

This ensures the client is uniquely and persistently identified.

## 4. Automated Cleanup After Prefix Changes

Even with correct renewal, a prefix change can still leave stale addresses on clients. The following script detects when the delegated prefix changes, removes old addresses from the LAN, and restarts odhcpd to send updated Router Advertisements.

### Script: `/root/ipv6-prefix-cleanup.sh`
```bash
#!/bin/sh

PREFIX_FILE="/tmp/wan6_prefix"
CURRENT_PREFIX=$(ubus call network.interface.wan6 status | jsonfilter -e '@["ipv6-prefix"][0].address')

if [ -z "$CURRENT_PREFIX" ]; then
    logger -t ipv6-cleanup "No IPv6 prefix on wan6, exiting"
    exit 0
fi

if [ -f "$PREFIX_FILE" ]; then
    OLD_PREFIX=$(cat "$PREFIX_FILE")
    if [ "$OLD_PREFIX" != "$CURRENT_PREFIX" ] && [ -n "$OLD_PREFIX" ]; then
        logger -t ipv6-cleanup "Prefix changed from $OLD_PREFIX to $CURRENT_PREFIX"
        # Remove all global addresses on LAN that match the old prefix
        ip -6 addr flush dev br-lan scope global to "${OLD_PREFIX}/64"
        # Restart odhcpd to send new RAs (including deprecation of old prefix)
        /etc/init.d/odhcpd restart
    fi
else
    logger -t ipv6-cleanup "Initial prefix $CURRENT_PREFIX"
fi

echo "$CURRENT_PREFIX" > "$PREFIX_FILE"
```

Make it executable: `chmod +x /root/ipv6-prefix-cleanup.sh`

### Trigger the script

You can run it periodically via cron, but a more elegant method is to use a **hotplug handler** that executes whenever the wan6 interface comes up or changes.

Create `/etc/hotplug.d/iface/99-ipv6-prefix`:
```bash
#!/bin/sh
[ "$INTERFACE" = "wan6" ] && [ "$ACTION" = "ifup" ] && /root/ipv6-prefix-cleanup.sh
```

This ensures cleanup runs automatically after each successful IPv6 acquisition.

If you prefer to keep the hourly cron job (e.g., to work around ISP renewal bugs), combine it with the cleanup script:
```
0 * * * * /root/ipv6-prefix-cleanup.sh
```
But note: the script alone does not force a renew – it only cleans up after a change. To trigger a renew, you can add `kill -SIGUSR1 $(pgrep odhcp6c)` before running the cleanup.

## 5. Advanced: Forcing Client Deprecation via RA

If Android clients still hold onto old addresses after the above, you can try to send an immediate Router Advertisement with zero lifetimes for the old prefix. This requires temporarily re-adding the prefix to the LAN interface (with no addresses) and triggering odhcpd. Here’s an enhanced version of the cleanup script that does this:

```bash
#!/bin/sh
# ... (same initial part as above) ...

if [ "$OLD_PREFIX" != "$CURRENT_PREFIX" ] && [ -n "$OLD_PREFIX" ]; then
    logger -t ipv6-cleanup "Prefix changed, deprecating $OLD_PREFIX"

    # Add a dummy address for the old prefix to make odhcpd advertise it with zero lifetime
    ip -6 addr add "${OLD_PREFIX}1/64" dev br-lan preferred_lft 0 valid_lft 0

    # Restart odhcpd to send RA with zero lifetimes
    /etc/init.d/odhcpd restart

    # Wait a moment for RA to be sent, then remove the dummy address
    sleep 2
    ip -6 addr del "${OLD_PREFIX}1/64" dev br-lan

    # Also flush any remaining global addresses from the old prefix
    ip -6 addr flush dev br-lan scope global to "${OLD_PREFIX}/64"
fi
```

This method tricks odhcpd into including the old prefix in the next RA with `preferred=0`, `valid=0`, prompting clients to immediately deprecate it.

## 6. When All Else Fails: Consider a Different DHCPv6 Client

If odhcp6c continues to misbehave, you could switch to `dhcpcd` (available in OpenWrt packages). It handles DHCPv6-PD more robustly in some environments. Install it and configure:

```sh
opkg update && opkg install dhcpcd
uci set network.wan6.proto='dhcpv6'
uci set network.wan6.client='dhcpcd'
uci commit network
```

But this is a more invasive change and may require additional options.

## 7. Summary of Recommendations

1. **First step**: Change `forceprefix` and `norelease` as described, and monitor for a few days.
2. **If issues persist**: Add stable DUID/IAID and the hotplug cleanup script.
3. **For immediate relief with your cron job**: Combine `kill -SIGUSR1` with the cleanup script to also flush old addresses and restart odhcpd.
4. **If Android stubbornness remains**: Implement the RA deprecation trick.

Remember to test each change gradually and check logs (`logread -e odhcp`) to confirm the behavior improves. The ultimate goal is a clean prefix transition without manual intervention.