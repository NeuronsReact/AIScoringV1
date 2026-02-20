Your symptoms are very characteristic of **IA_NA + IA_PD desynchronization with a single /64 ISP delegation**. Let’s analyze it precisely.

---

# 1️⃣ What Is Actually Happening

From your abnormal state:

* WAN6 receives:

  * Old `/128` IA_NA
  * New `/64` global address (likely via RA or IA_NA)
* But IA_PD:

  * Still bound to **old /64 prefix**
* DHCPv6 server replies:

  ```
  IA_PD status 'No Binding'
  IA_PD status 'Not On Link'
  ```

This means:

> The ISP has dropped your previous PD binding, but your router is trying to RENEW instead of REBIND or REQUEST.

That leaves OpenWrt in a half-broken state:

* Upstream has moved on
* Your CPE still advertises old delegated prefix
* `odhcpd` detects no valid default route → sets RA lifetime = 0
* Android keeps old SLAAC addresses because:

  * Preferred lifetime not expired
  * Router does not properly deprecate them

This is a classic problem when ISP only provides **single /64 PD**, not a larger block like /60 or /56.

---

# 2️⃣ Why Your Cron SIGUSR1 “Works”

`kill -SIGUSR1 $(pgrep odhcp6c)`

SIGUSR1 forces **renew immediately**.

This works because:

* odhcp6c finally performs proper rebind
* gets new IA_NA and IA_PD
* LAN reassigns prefix

But:

* It is time-based
* Renewal failure is event-based
* Android still keeps old SLAAC addresses

So it’s a mitigation, not a fix.

---

# 3️⃣ Root Cause

Your ISP:

* Gives only **/64 PD**
* Also assigns WAN global address from same /64
* Does not gracefully handle PD renew
* Returns "No Binding / Not On Link"

This is ISP-side state loss.

The real problem is:

> OpenWrt does not properly abandon old IA_PD when server says “No Binding”.

---

# 4️⃣ Why Android Keeps Old Addresses

Android uses SLAAC only.

When:

* RA still advertises old prefix
* Or prefix preferred lifetime > 0

Android will:

* Keep old IPv6
* Continue using it until it becomes deprecated

Restarting LAN does NOT invalidate SLAAC addresses on clients.

Only:

* RA with preferred lifetime = 0
* Or interface disconnect
* Or waiting for preferred lifetime expiry

will remove them.

---

# 5️⃣ The Correct Engineering Fix

Instead of cron, you want **state-driven recovery**.

## Option A — Remove `norelease '1'`  ⚠️ Important

You currently have:

```bash
option norelease '1'
```

This prevents proper DHCPv6 release.

Remove it.

Let odhcp6c release binding properly.

---

## Option B — Force full rebind on No Binding

Create hotplug handler:

```
/etc/hotplug.d/iface/99-wan6-recover
```

Example:

```bash
#!/bin/sh

[ "$INTERFACE" = "wan6" ] || exit 0
[ "$ACTION" = "ifupdate" ] || exit 0

sleep 5

if ! ubus call network.interface.wan6 status | grep -q '"ipv6-prefix"'; then
    logger "WAN6 PD missing — restarting wan6"
    ifdown wan6
    sleep 3
    ifup wan6
fi
```

This reacts to real failure.

No cron.

---

## Option C — Fix Android Old Prefix Retention

When prefix changes, force RA deprecation.

Set in:

```
/etc/config/dhcp
```

Under LAN:

```bash
option ra_default '1'
option ra_preference 'high'
option ra_lifetime '1800'
```

Then ensure:

```
option ra_management '1'
```

If still problematic:

You may need to:

```bash
/etc/init.d/odhcpd restart
```

when prefix changes.

Better solution: monitor PD change and restart odhcpd.

---

# 6️⃣ Important: Your `forceprefix '1'`

You have:

```bash
option forceprefix '1'
```

This is usually unnecessary and can cause prefix mismatch behavior.

Try removing:

```bash
option forceprefix
```

Unless ISP requires it.

---

# 7️⃣ About MTU 1480

You manually set:

```bash
option mtu '1480'
```

If ISP is PPPoE, correct.
If not, unnecessary.

Not directly related, but verify.

---

# 8️⃣ Why Default Route Disappears

Log:

```
No default route present, setting ra_lifetime to 0!
```

This occurs because:

* Your router temporarily has no valid IPv6 default route
* So it tells LAN: “Don’t use me as IPv6 gateway”

Correct behavior.

But indicates upstream instability.

---

# 9️⃣ The Cleanest Configuration for Single /64 ISP

For ISPs that only give one /64:

Minimalistic and stable:

```bash
config interface 'wan6'
        option device '@wan'
        option proto 'dhcpv6'
        option reqaddress 'try'
        option reqprefix '64'
```

Remove:

* norelease
* forceprefix
* noslaaconly

Then:

```
uci commit network
/etc/init.d/network restart
```

---

# 🔟 The Real Long-Term Solution

Best solution is:

Ask ISP for:

* /60
* or /56 delegation

Single /64 PD is fundamentally fragile.

With /60:

* WAN uses one /64
* LAN gets separate /64
* No IA_PD conflict
* No Android confusion

---

# 1️⃣1️⃣ What I Would Do (Production-Grade Fix)

1. Remove:

   * norelease
   * forceprefix
   * noslaaconly

2. Set:

   ```
   option reqprefix '64'
   ```

3. Add hotplug recovery script.

4. Restart odhcpd when PD changes.

5. If still unstable → escalate to ISP.

---

# 1️⃣2️⃣ Why This Is Not an OpenWrt Bug

This is interaction between:

* DHCPv6 stateful PD
* ISP state reset
* Single /64 deployment
* SLAAC client behavior (Android)

This scenario is well known in ISP-grade CPE deployments.

---

If you want, I can:

* Design a fully event-driven PD monitoring script
* Or analyze packet flow (SOLICIT / REQUEST / RENEW / REBIND) in detail
* Or propose a completely different architecture (SLAAC-only WAN, no PD)

Tell me which depth you want.
