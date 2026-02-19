It sounds like your ISP is performing a "prefix change" without properly signaling the expiration of the old one, or your `odhcp6c` client is getting stuck in a state where it can't reconcile the new lease because of that "No Binding" error from the server.

When you send `SIGUSR1`, you are forcing a **DHCPv6 Renew**, which is why the router gets the new info, but your Android devices are stubborn because they haven't been told the old prefix is officially **deprecated**.

---

## Why your Android clients are "Sticky"

Android is notorious for its strict adherence to **SLAAC** (Stateless Address Autoconfiguration). If the router doesn't explicitly send a Router Advertisement (RA) with a **Preferred Lifetime of 0** for the old prefix, the Android device will keep it until it expires naturally—which could be hours or days.

### 1. Fix the "No Binding" issue (The Root Cause)

The "No Binding" error often happens because the ISP's DHCPv6 server thinks your session has expired or doesn't match the DUID. Instead of just renewing, you might need to force a fresh solicitation.

Try changing your **WAN6** settings in `/etc/config/network`:

* Set `option reqprefix 'auto'` (or specifically `64`).
* Add `option norelease '0'` to ensure that when the interface stops, it tells the ISP to release the lease.
* **Crucial:** Ensure `option delegate '1'` is on the WAN6 interface.

---

## 2. A Better "Watchdog" Script

Instead of a blind hourly cron job, use a script that checks for the "No Binding" error or a mismatch in the `ubus` output. Put this in `/root/check_ipv6.sh`:

```bash
#!/bin/sh
# Check if WAN6 has a valid prefix assigned to LAN
PREFIX=$(ubus call network.interface.wan6 status | jsonfilter -e '@["ipv6-prefix"][0].address')

if [ -z "$PREFIX" ]; then
    echo "IPv6 Prefix missing, restarting wan6..."
    ifup wan6
fi

```

**Why `ifup wan6`?** Unlike `SIGUSR1`, `ifup` tears down the interface and brings it back up. This triggers OpenWrt’s `netifd`, which should automatically send out a "final" RA to your LAN clients with a lifetime of 0 for the old prefix, effectively flushing them.

---

## 3. Forcing Android to Drop Old IPs

If the old IPs still stick around, you need to tune the **RA (Router Advertisement)** behavior on the **LAN** interface.

Edit `/etc/config/dhcp`:

```config
config dhcp 'lan'
    option interface 'lan'
    option ra 'server'
    option ra_management '1'
    option ra_deprecate '1'  # This is the key!
    option ra_slaac '1'

```

* **`ra_deprecate '1'`**: When a prefix becomes invalid or the interface goes down, OpenWrt will send an RA telling clients the old prefix is no longer preferred.

---

## 4. The "Nuclear" Option: Scripted Prefix Flush

If the ISP changes the prefix but the old one stays in the routing table, you can automate a flush. Add this to your cron instead:

```bash
# This restarts the network subsystem cleanly
/etc/init.d/network restart

```

However, a more surgical approach is to use the `action` scripts in `/etc/hotplug.d/iface/`, which run automatically whenever `wan6` comes up, ensuring the routing table is clean.

### Summary of Recommendations

| Problem | Solution |
| --- | --- |
| **"No Binding" Error** | Change `odhcp6c` settings to `norelease 0` and check DUID stability. |
| **Stale Android IPs** | Set `option ra_deprecate '1'` in LAN dhcp settings. |
| **Hourly Timing** | Use a script to check `ubus` status every 5 mins rather than a blind `kill`. |

Would you like me to help you write a more advanced **hotplug script** that detects the prefix change and automatically flushes the old routes?