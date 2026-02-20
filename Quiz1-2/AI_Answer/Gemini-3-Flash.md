It looks like your ISP is performing "unannounced" prefix changes or has a very short/unstable lease environment where the DHCPv6 server loses track of your session (hence the `No Binding` and `Not On Link` errors).

When the prefix changes but the old one hasn't expired, your Android devices suffer from **"Stale Prefix"** syndrome. Android is notorious for sticking to the first valid global IPv6 address it gets via SLAAC until the `preferred_lft` (Preferred Lifetime) reaches zero.

Here is a breakdown of how to fix the configuration to handle these transitions more gracefully.

---

## 1. Optimize the WAN6 Configuration

Your current config is trying to force certain behaviors, but we can make it more resilient to the ISP's "No Binding" errors.

**Modify `/etc/config/network`:**

* Change `reqprefix` to `64` (since you know that's what they give).
* Add `solicit_interval`.

```bash
config interface 'wan6'
        option device '@wan'
        option proto 'dhcpv6'
        option reqaddress 'try'
        option reqprefix '64'      # Specify 64 instead of auto
        option norelease '1'
        option forceprefix '1'
        # Reduce the time odhcp6c waits before retrying a solicit
        option solicit_interval '15' 

```

---

## 2. Fix the "Stale Prefix" on LAN (Android fix)

The reason your Android devices keep the old IP is that the Router Advertisement (RA) sent by OpenWrt still considers the old prefix "valid." You need to tell the LAN to immediately deprecate old prefixes when they disappear from the upstream.

**Modify `/etc/config/dhcp`:**
Ensure your `lan` section has these options to aggressively prune old prefixes:

```bash
config dhcp 'lan'
        option interface 'lan'
        option ra 'server'
        option dhcpv6 'server'
        option ra_management '1'
        option ra_advrouter '1'
        # These are key for clearing old prefixes:
        option ra_slaac '1'
        list ra_flags 'managed-config'
        list ra_flags 'other-config'
        # Tells odhcpd to send RA with preferred_lft 0 for old prefixes
        option ra_preference 'high' 

```

---

## 3. The "Scripted" Fix (Better than Crontab)

Instead of a blind cron job, you should use a **hotplug script**. This script triggers only when the interface actually changes or fails, and it can force a "clean" restart of the network logic which LuCI does behind the scenes.

Create a file at `/etc/hotplug.d/iface/99-ipv6-refresh`:

```bash
#!/bin/sh
# Trigger only on wan6 events
[ "$INTERFACE" = "wan6" ] || exit 0

if [ "$ACTION" = "ifup" ] || [ "$ACTION" = "ifupdate" ]; then
    # Restart odhcpd to ensure RA is broadcasting the NEW prefix only
    /etc/init.d/odhcpd restart
fi

```

*Make sure to run `chmod +x /etc/hotplug.d/iface/99-ipv6-refresh`.*

---

## 4. Why Android still fails

Android uses the **RFC 4862** implementation for SLAAC. If your router sends an RA where the `Preferred Lifetime` is 0 but the `Valid Lifetime` is still > 0, Android will keep the address but mark it as "deprecated." However, it might still try to use it for existing connections.

By restarting `odhcpd` via the hotplug script above, you force a new RA sequence. If the ISP's old prefix is truly gone from the OpenWrt routing table, `odhcpd` will stop announcing it, and it will eventually time out on the phone.

### Summary of the "Abnormal Status"

The log `Server returned IA_PD status 'No Binding'` means the ISP's server forgot your DUID/IAID association.

1. The ISP likely expects a **Renew** but you are sending a **Rebind**, or vice versa.
2. Setting `option norelease '1'` is good, but if the ISP is picky, you might actually need to set it to `0` to force a "fresh" start when the interface bounces.

**Would you like me to provide a script that specifically monitors the `ubus` status and restarts the interface only when the "No Binding" error is detected?**