This is a classic DHCPv6 prefix delegation instability issue combined with Android's stubborn SLAAC behavior. Let me break down what's happening and suggest improvements.

## What's actually going on

The ISP's DHCPv6 server is losing your binding (likely due to a BNG/BRAS session reset or a bug on their side), which causes it to reject your renewal with "No Binding" and "Not On Link." Your router then has a stale /64 that it continues advertising via RA, and new clients pick up a new prefix — but Android devices that already have a SLAAC address from the old prefix continue using it until its valid lifetime expires, because Android ignores RA with lifetime=0 for already-configured addresses (this is a long-standing Android behavior).

## Better approaches

**1. Trigger renew on actual failure, not on a timer**

Instead of renewing every hour blindly, detect the failure and act immediately. You can watch the log:

```sh
# /etc/hotplug.d/iface/99-dhcp6-watchdog
# Not ideal for this — better to use a script polling odhcp6c logs
```

A more practical approach is a watchdog script that checks prefix validity:

```sh
#!/bin/sh
# /usr/local/bin/wan6-watchdog.sh

IFACE="wan6"
LOG_TAG="wan6-watchdog"

status=$(ubus call network.interface.${IFACE} status 2>/dev/null)
prefix_count=$(echo "$status" | jsonfilter -e '@["ipv6-prefix"][*].address' 2>/dev/null | wc -l)
preferred=$(echo "$status" | jsonfilter -e '@["ipv6-prefix"][0].preferred' 2>/dev/null)

if [ -z "$preferred" ] || [ "$preferred" -lt 60 ]; then
    logger -t "$LOG_TAG" "Prefix preferred lifetime low or missing ($preferred), triggering renew"
    kill -SIGUSR1 $(pgrep odhcp6c)
fi
```

Then run it every 5 minutes via cron: `*/5 * * * * /usr/local/bin/wan6-watchdog.sh`

This is reactive to actual degradation rather than running on an arbitrary schedule.

**2. The Android problem — this is the hard part**

Android ignores RA with PIO (Prefix Information Option) lifetime set to 0 for addresses it has already configured. The RFC technically allows a router to deprecate a prefix this way, but Android simply doesn't honor it for existing addresses. Your options are:

**Option A: Aggressive RA deprecation + long wait.** Set the old prefix's valid lifetime to 0 in a forced RA. OpenWrt can do this but only partially — `odhcp6c` and `odhcpd` don't give you fine-grained control over per-prefix RA lifetimes for stale prefixes. In practice this rarely works on Android anyway.

**Option B: Use a ULA (Unique Local Address) as a stable fallback.** Assign a `fd::/64` ULA to your LAN in parallel. Android devices will have both a ULA and a GUA. For internal traffic they'll use ULA. When the GUA changes, it matters less because outbound traffic from Android will prefer the new GUA from the new prefix anyway (via address selection rules — RFC 6724 prefers longer valid prefixes). The old address just becomes unused faster.

To add ULA on OpenWrt, in `/etc/config/network`:
```
config interface 'lan'
    option ula_prefix 'fd<yourrandom>::/48'   # OpenWrt generates this automatically
```
OpenWrt actually auto-generates a ULA prefix in `system` config — check `uci get network.globals.ula_prefix`. Make sure `odhcpd` is advertising it.

**Option C: Shorten the RA valid lifetime proactively.** If you shorten the RA valid/preferred lifetime to something like 30 minutes, Android devices will naturally stop using stale addresses sooner after a prefix change. The tradeoff is more frequent RA traffic. In `/etc/config/dhcp` for your LAN:

```
config dhcp 'lan'
    option ra_lifetime '1800'     # 30 min valid lifetime in RA
    option ra_useleasetime '1'    # tie RA lifetime to DHCP lease time
```

Setting `ra_lifetime` shorter means when the prefix changes, Android will drop the old address within `ra_lifetime` seconds without any manual intervention, as long as odhcpd sends a RA with the old prefix marked as deprecated or simply stops including it.

**Option D: Force a RA with the old prefix zeroed out right after renewal.** After `kill -SIGUSR1`, once the new prefix is confirmed, you could send a crafted RA deprecating the old prefix using `radvd` or a raw packet tool — but this is complex and fragile on OpenWrt.

## Recommended combined approach

1. Use the watchdog script (every 5 min) instead of the hourly blind renew — catches failures faster.
2. Set `ra_lifetime` to 1800 (30 min) on LAN so Android devices cycle off stale addresses within half an hour automatically.
3. Verify your ULA prefix is being advertised — it provides stability for internal communication regardless of GUA churn.
4. Long term: report the "No Binding" issue to your ISP. This is a server-side problem; a stable ISP DHCPv6 setup shouldn't be dropping bindings like this.

The Android behavior is a known limitation — there's no clean in-network fix that forces Android to drop a valid SLAAC address before its lifetime expires. Shortening RA lifetimes is the most practical mitigation.