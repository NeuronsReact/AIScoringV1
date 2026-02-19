You are hitting a classic DHCPv6-PD edge case: the ISP is invalidating the existing IA_PD binding, but your LAN-side RA lifecycle is not cleanly deprecating the old prefix. As a result, downstream clients (especially Android) retain the old SLAAC address and continue selecting it for source address selection.

Let’s dissect this rigorously.

---

# 1️⃣ What the ISP is Doing

These log lines are decisive:

```
odhcp6c: Server returned IA_PD status 'No Binding'
odhcp6c: Server returned IA_PD status 'Not On Link'
```

Interpretation:

* **No Binding** → The server no longer recognizes your delegated prefix.
* **Not On Link** → The prefix you are trying to renew is not valid for your current link context.

This means:

* Your previous IA_PD (/64) is invalid.
* ISP likely dropped your PD state (session reset, BRAS reload, DHCPv6 state loss).
* Your CPE should discard the old prefix immediately.

Your workaround:

```
kill -SIGUSR1 $(pgrep odhcp6c)
```

is correct — SIGUSR1 forces `odhcp6c` to send a Renew/Rebind. That explains why WAN6 gets a new IA_NA and IA_PD correctly.

So WAN side is behaving.

The problem is LAN side.

---

# 2️⃣ Why Android Keeps the Old IPv6 Address

This is purely **Router Advertisement (RA) lifetime behavior**.

Android does:

* SLAAC only (no DHCPv6)
* Obeys RA lifetimes strictly
* Does NOT instantly remove an address unless:

  * Valid Lifetime becomes 0
  * Interface goes down
  * Router lifetime expires

If OpenWrt:

* Removes old PD internally
* But does NOT send an RA with:

  ```
  valid lifetime = 0
  preferred lifetime = 0
  ```

then clients will:

* Keep the old address
* Keep using it until Valid Lifetime expires

And since your original PD shows:

```
"preferred": 105255
"valid": 191655
```

That’s ~29 hours preferred, ~53 hours valid.

Android will absolutely continue using it.

---

# 3️⃣ Why LuCI Toggle Fixes It

When you change an option in LuCI:

* `netifd` reloads
* `odhcpd` restarts
* LAN interface is bounced
* New RA is sent

That forces:

* Router lifetime reset
* Clients re-evaluate prefix list
* Old prefix may be dropped

This confirms the problem is RA lifecycle, not DHCPv6 itself.

---

# 4️⃣ Root Cause

When IA_PD is rejected:

`odhcp6c` updates WAN6

BUT

`netifd` does not fully tear down the old delegated prefix on LAN before installing the new one.

So:

* Kernel drops old route
* But `odhcpd` may not send a zero-lifetime RA for the old prefix

This is a known OpenWrt behavior depending on version.

---

# 5️⃣ Why "Extend the /64 to prefix" Doesn't Help

That option only affects how PD is used when no IA_PD is provided.

You already get IA_PD.

Your issue is prefix lifecycle management, not prefix derivation.

---

# 6️⃣ Correct Engineering-Level Fix

You need to ensure that when IA_PD changes:

1. Old prefix is deprecated (RA lifetime = 0)
2. New prefix is advertised
3. Clients re-evaluate source addresses

There are 4 possible approaches.

---

## ✅ Option A — Restart LAN Interface When PD Changes (Cleanest)

Instead of only signaling `odhcp6c`, do:

```
ifdown wan6
ifup wan6
```

OR more aggressive:

```
/etc/init.d/network reload
```

This forces:

* netifd to re-evaluate delegated prefixes
* odhcpd to resend RA properly

This usually fixes Android retention.

---

## ✅ Option B — Restart odhcpd After PD Refresh

Add to cron:

```
kill -SIGUSR1 $(pgrep odhcp6c)
/etc/init.d/odhcpd restart
```

This ensures new RA cycle starts.

---

## ✅ Option C — Force RA Lifetime Short

In `/etc/config/dhcp` under `lan`:

```
config dhcp 'lan'
    option ra_default '1'
    option ra_management '0'
    option ra_preference 'medium'
    option ra_maxinterval '30'
    option ra_lifetime '90'
```

Short RA lifetime makes stale prefixes expire faster.

Still not perfect, but mitigates.

---

## ✅ Option D — Use odhcp6c Script Hook (Most Correct)

Edit:

```
/lib/netifd/proto/dhcpv6.sh
```

Or create hotplug script:

```
/etc/hotplug.d/iface/99-pd-refresh
```

Trigger:

```
[ "$ACTION" = ifupdate ] && [ "$INTERFACE" = "wan6" ] && {
    /etc/init.d/odhcpd restart
}
```

This makes behavior deterministic.

---

# 7️⃣ Why Android Specifically Is Stubborn

Android:

* Uses RFC 6724 source address selection
* Prefers "stable privacy" address
* Does NOT immediately re-run DAD unless forced

So old address may stay preferred even after new PD appears.

Only zero-valid-lifetime RA fully removes it.

---

# 8️⃣ What I Recommend (Production-Grade)

Replace your cron job with:

```
0 * * * * {
    kill -SIGUSR1 $(pgrep odhcp6c)
    sleep 5
    /etc/init.d/odhcpd restart
}
```

If still problematic:

Switch to:

```
ifdown wan6 && ifup wan6
```

That is architecturally cleaner than partial signaling.

---

# 9️⃣ If You Want to Fully Diagnose

During abnormal state, run:

```
ubus call network.interface.wan6 status
ip -6 addr
ip -6 route
logread | grep odhcp
```

Specifically check:

* Does old prefix still appear in:

  ```
  ip -6 addr show br-lan
  ```
* Does odhcpd still advertise it?

That tells us whether the bug is in:

* netifd
* odhcp6c
* odhcpd
* or ISP behavior

---

# 🔎 Final Technical Summary

Your ISP drops IA_PD binding.
odhcp6c renew fixes WAN.
OpenWrt does not properly deprecate old PD on LAN.
Android retains old SLAAC address due to long valid lifetime.
Restarting LAN-side RA service resolves it.

This is not a DHCPv6 problem.
It is a Router Advertisement lifecycle synchronization issue.

---

If you'd like, tell me:

* OpenWrt version
* Are you using DSA?
* Are you using relay mode or server mode for RA?

Then we can tune this properly rather than relying on cron hacks.
