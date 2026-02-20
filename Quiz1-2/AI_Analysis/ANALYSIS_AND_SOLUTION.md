# IPv6 DHCPv6-PD Problem Analysis and Solution
**Date:** February 20, 2026  
**Context:** Quiz1-2 Problem - ISP Prefix Change with Stale Android Addresses

---

## 1. Problem Summary

### Core Issue
Your OpenWrt router experiences DHCPv6 Prefix Delegation (PD) renewal failures with your ISP. When the ISP changes the prefix:
1. Old `/64` prefix remains assigned to LAN interface
2. New `/64` prefix is assigned to WAN6
3. Android clients continue using old IPv6 addresses indefinitely

### Root Cause
- ISP returns `No Binding` and `Not On Link` errors during PD renewal
- Your ISP provides only `/64` PD (not `/60` or `/56`)
- odhcp6c doesn't properly abandon old IA_PD when server says "No Binding"
- Android caches SLAAC addresses until preferred lifetime expires (can be hours)

### Symptoms
```
Server returned IA_PD status 'No Binding'
Server returned IA_PD status 'Not On Link'
No default route present, setting ra_lifetime to 0!
```

---

## 2. AI Answer Analysis

### 2.1 DeepSeek-3.x-web

**Strengths:**
- Comprehensive configuration adjustments with exact UCI commands
- Provides automated cleanup script that detects prefix changes
- Explains the DUID/IAID stability issue
- Offers multiple solution tiers from simple to advanced

**Weaknesses:**
- Recommends generating random DUID which might worsen stability
- The "dummy address" deprecation trick is complex and might cause issues
- Doesn't address why `forceprefix 0` vs `1` matters

**Verdict:** Good overall approach but some recommendations are overkill

---

### 2.2 Gemini-3-Flash

**Strengths:**
- Simple configuration change (`reqprefix 64` instead of `auto`)
- Good explanation of Android's SLAAC behavior
- Hotplug script approach (event-driven, not cron-based)

**Weaknesses:**
- Limited scope - doesn't address the core PD state issue
- Recommends `forceprefix 1` which might be problematic
- The DHCP configuration suggestions (ra_slaac, ra_preference) are syntax errors in OpenWrt

**Verdict:** Oversimplified, some incorrect syntax

---

### 2.3 Kimi_K2.5-Instant-websearch

**Strengths:**
- Most comprehensive solution with multiple approaches
- Correctly identifies root cause (IA_NA + IA_PD desynchronization)
- Provides event-driven detection script
- Explains why SIGUSR1 cronjob is imperfect
- Practical LAN bounce script for Android

**Weaknesses:**
- Solution 5 (reqpreflifetime) - option doesn't exist in odhcp6c
- Solution 4 (noserverunicast, strict_rfc7550) - these options don't exist
- Multiple "experimental" recommendations that might not work

**Verdict:** Best analysis, but some solution options are invalid

---

### 2.4 OpenAI_ChatGPT-5.x-web

**Strengths:**
- Excellent technical analysis of the state machine
- Clear explanation of RENEW vs REBIND behavior
- Recommends removing `norelease 1` (correct)
- Suggests minimal working configuration
- Realistic about ISP limitation (single /64)

**Weaknesses:**
- Doesn't provide complete scripts, only conceptual guidance
- The "ask ISP for /60" is not actionable
- Missing concrete automation examples

**Verdict:** Best analysis, but needs implementation details

---

## 3. Step-by-Step Solution

Based on the analysis of all AI answers, here is the recommended solution:

### Step 1: Optimize Network Configuration

**File:** `/etc/config/network`

```bash
# For wan6 interface, change from:
config interface 'wan6'
        option device '@wan'
        option proto 'dhcpv6'
        option reqaddress 'try'
        option reqprefix 'auto'
        option norelease '1'
        option forceprefix '1'
        option noslaaconly '1'

# To:
config interface 'wan6'
        option device '@wan'
        option proto 'dhcpv6'
        option reqaddress 'try'
        option reqprefix '64'
        option noslaaconly '1'
```

**Apply changes:**
```bash
uci commit network
/etc/init.d/network restart
```

**Rationale:**
- Remove `norelease 1` → allows proper release when interface goes down
- Remove `forceprefix 1` → prevents confusing the server with duplicate requests
- Change `reqprefix auto` to `reqprefix 64` → explicit request since you know the ISP gives /64

---

### Step 2: Create Hotplug Event Handler

**File:** `/etc/hotplug.d/iface/99-wan6-recover`

```bash
#!/bin/sh
# Event-driven recovery for WAN6 PD failures

[ "$INTERFACE" = "wan6" ] || exit 0
[ "$ACTION" = "ifupdate" ] || [ "$ACTION" = "ifup" ] || exit 0

# Wait for interface to stabilize
sleep 5

# Check if prefix is missing or stale (multiple /64s or old /128 with new /64)
PREFIX_COUNT=$(ubus call network.interface.wan6 status | jsonfilter -e '@["ipv6-prefix"]' | grep -c '"mask": 64' 2>/dev/null || echo "0")

if [ "$PREFIX_COUNT" -eq 0 ]; then
    logger -t wan6-recover "No PD prefix detected, restarting wan6"
    ifdown wan6
    sleep 3
    ifup wan6
elif [ "$PREFIX_COUNT" -gt 1 ]; then
    logger -t wan6-recover "Multiple PD prefixes detected ($PREFIX_COUNT), cleaning up"
    # Trigger renew
    killall -SIGUSR1 odhcp6c 2>/dev/null
    sleep 3
    # If still stale after 3 seconds, full restart
    PREFIX_COUNT_AFTER=$(ubus call network.interface.wan6 status | jsonfilter -e '@["ipv6-prefix"]' | grep -c '"mask": 64' 2>/dev/null || echo "0")
    if [ "$PREFIX_COUNT_AFTER" -gt 1 ]; then
        ifdown wan6
        sleep 3
        ifup wan6
    fi
fi
```

**Make executable:**
```bash
chmod +x /etc/hotplug.d/iface/99-wan6-recover
```

---

### Step 3: Create Prefix Change Detection Script

**File:** `/usr/local/bin/ipv6-prefix-cleanup.sh`

```bash
#!/bin/sh
# Detects prefix changes and cleans up stale addresses

PREFIX_FILE="/tmp/wan6_prefix"
CURRENT_PREFIX=$(ubus call network.interface.wan6 status | jsonfilter -e '@["ipv6-prefix"][0].address' 2>/dev/null)

if [ -z "$CURRENT_PREFIX" ]; then
    logger -t ipv6-cleanup "No IPv6 prefix on wan6"
    exit 0
fi

if [ -f "$PREFIX_FILE" ]; then
    OLD_PREFIX=$(cat "$PREFIX_FILE")
    if [ "$OLD_PREFIX" != "$CURRENT_PREFIX" ] && [ -n "$OLD_PREFIX" ]; then
        logger -t ipv6-cleanup "Prefix changed: $OLD_PREFIX -> $CURRENT_PREFIX"
        
        # Option A: Restart odhcpd to send updated RAs
        /etc/init.d/odhcpd restart
        
        # Option B (Nuclear): Bounce LAN interface to force Android refresh
        # Uncomment the following if Android still has stale addresses:
        # ifdown lan
        # sleep 2
        # ifup lan
        
        # Wait for odhcpd to settle
        sleep 2
        
        # Remove old addresses from LAN that match old prefix
        if [ -n "$OLD_PREFIX" ]; then
            ip -6 addr flush dev br-lan scope global to "${OLD_PREFIX}/64" 2>/dev/null
        fi
    fi
else
    logger -t ipv6-cleanup "Initial prefix: $CURRENT_PREFIX"
fi

echo "$CURRENT_PREFIX" > "$PREFIX_FILE"
```

**Make executable:**
```bash
chmod +x /usr/local/bin/ipv6-prefix-cleanup.sh
```

---

### Step 4: Trigger on Prefix Changes

**File:** `/etc/hotplug.d/iface/98-ipv6-cleanup`

```bash
#!/bin/sh
# Trigger cleanup when WAN6 prefix actually changes

[ "$INTERFACE" = "wan6" ] || exit 0
[ "$ACTION" = "ifupdate" ] || [ "$ACTION" = "ifup" ] || exit 0

# Wait for DHCPv6 to complete
sleep 10

# Run cleanup script
/usr/local/bin/ipv6-prefix-cleanup.sh
```

**Make executable:**
```bash
chmod +x /etc/hotplug.d/iface/98-ipv6-cleanup
```

---

### Step 5: Modify Crontab (Backup Solution)

Keep your existing cron job but enhance it:

```bash
# Edit crontab
crontab -e

# Change from:
0 * * * * kill -SIGUSR1 $(pgrep odhcp6c)

# To:
0 * * * * /usr/local/bin/ipv6-prefix-cleanup.sh
```

This runs hourly but now also cleans up stale addresses.

---

### Step 6: Test the Solution

```bash
# 1. Apply all changes
chmod +x /etc/hotplug.d/iface/*

# 2. Monitor logs
logread -f -e odhcp6c -e odhcpd -e wan6-recover -e ipv6-cleanup &

# 3. Force a renewal to test
kill -SIGUSR1 $(pgrep odhcp6c)

# 4. Watch for prefix change in logs
ubus call network.interface.wan6 status | jsonfilter -e '@["ipv6-prefix"][0].address'
```

---

## 4. Why These Solutions Work

### Event-Driven vs Cron-Based
- **Old approach:** Hourly SIGUSR1 - blind, wasteful
- **New approach:** React only when interface actually changes

### Cleanup on Prefix Change
- Detects when `OLD_PREFIX != NEW_PREFIX`
- Forces odhcpd to restart (sends new RAs)
- Optionally bounces LAN to force Android to drop stale addresses

### Removing norelease=1
- Previously: Interface down → no RELEASE sent → ISP keeps stale binding
- Now: Interface down → RELEASE sent → clean state on next request

---

## 5. Expected Results

| Scenario | Before | After |
|----------|--------|-------|
| ISP changes prefix | Old + new prefixes on WAN6 | Only new prefix on WAN6 |
| Android clients | Keep old IPs for hours/days | Drop old IPs within minutes |
| Recovery time | Up to 1 hour (cron) | Immediate (event-driven) |
| Log entries | Multiple "No Binding" errors | Single recovery attempt |

---

## 6. Monitoring Commands

```bash
# Check current prefix
ubus call network.interface.wan6 status | jsonfilter -e '@["ipv6-prefix"][0].address'

# Check LAN addresses
ip -6 addr show dev br-lan

# View logs
logread -e odhcp6c | tail -20

# Test prefix change detection
/usr/local/bin/ipv6-prefix-cleanup.sh
```

---

## 7. Troubleshooting

### If still seeing stale prefixes:
1. Check if hotplug scripts are executing: `logread -e wan6-recover`
2. Verify scripts are executable: `ls -la /etc/hotplug.d/iface/9*`
3. Manual test: `/usr/local/bin/ipv6-prefix-cleanup.sh`

### If Android still keeps old addresses:
1. Uncomment the LAN bounce section in the cleanup script
2. Increase wait time before `ifdown lan`
3. Consider reducing RA lifetimes (advanced)

### If ISP continues to give "No Binding":
1. Contact ISP - this indicates their DHCPv6 server has issues
2. Ask if they support larger prefix delegation (/60 or /56)
3. Consider using SLAAC-only mode (no PD) as fallback

---

## 8. Summary of Changes

| File | Purpose |
|------|---------|
| `/etc/config/network` | Remove `norelease=1`, `forceprefix=1`; set `reqprefix=64` |
| `/etc/hotplug.d/iface/99-wan6-recover` | Event-driven recovery on PD failures |
| `/etc/hotplug.d/iface/98-ipv6-cleanup` | Trigger cleanup when prefix changes |
| `/usr/local/bin/ipv6-prefix-cleanup.sh` | Core cleanup logic |
| Crontab | Backup hourly trigger (enhanced) |

---

**Note:** The AI answers had mixed quality. The Kimi answer provided the best analysis but some invalid options. The ChatGPT answer was technically sound but lacked implementation. This solution combines the best insights from all answers with validated OpenWrt options.
