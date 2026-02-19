The problem lies in how `odhcp6c` (the IPv6 DHCPv6 client on OpenWrt) handles the specific error codes returned by your ISP, combined with the difference between "Renewing" a lease and "Requesting" a new one.
Here is the breakdown of why your current situation happens and how to fix it permanently.
### Root Cause Analysis
1.  **The "No Binding" Error**: 
    Your logs show `Server returned IA_PD status 'No Binding'`. This means your ISP's DHCPv6 server has lost the record of your lease (maybe due to a server reboot, a session timeout on their side, or a mismatch in DUID). 
    When `odhcp6c` tries to **Renew** (Renew/Rebind) the existing lease, the server rejects it saying "I don't know you."
2.  **Why `SIGUSR1` is not enough**:
    The command `kill -SIGUSR1` tells `odhcp6c` to "Renew the current lease immediately."
    Since the server has lost the binding, a "Renew" is impossible. The correct technical action for a client upon receiving "No Binding" is to stop the current session and start a fresh **Solicit** process (requesting a new lease from scratch).
    `odhcp6c` should theoretically do this automatically, but in many versions, it gets stuck in a retry loop or updates the address (IA_NA) but fails to recover the prefix (IA_PD), leading to that "Abnormal" state where you have a /128 address but a broken/old /64 prefix.
3.  **The Android Issue**:
    When your router gets stuck, it eventually forces a new prefix. Android devices are designed to be very stubborn with IPv6 addresses to maintain connections. If the router does not explicitly send a "Router Advertisement" saying "The old prefix is now invalid (Lifetime 0)", Android will keep the old IP address until it expires (which could take hours). Since your router process got stuck, it likely failed to send the proper "deprecation" signal to the LAN clients.
---
### Solutions
Do not use a crontab to kill the process blindly. Instead, fix the client behavior and use a smart watchdog.
#### Step 1: Ensure DUID Persistence (Crucial)
If your router reboots or the process restarts and sends a *different* DUID (Client ID), the ISP will return "No Binding" because it doesn't recognize the new ID. OpenWrt stores DUIDs in `/var/` by default, which is cleared on reboot.
Edit your WAN6 interface configuration to ensure a persistent DUID.
Edit `/etc/config/network`:
Find the `wan6` interface section (or the interface handling DHCPv6). Add or modify the `duid` option to use a fixed value stored in flash memory.
```config
config interface 'wan6'
    option device '@wan'
    option proto 'dhcpv6'
    # ... other options ...
    option duid '00:03:00:01:XX:XX:XX:XX:XX:XX' 
    # Replace XX... with your device's MAC or a permanent hex string.
    # This ensures the ISP always recognizes you after a restart.
```
*Note: You can find your current DUID in `/var/odhcp6c_duid` to copy it.*
#### Step 2: Replace the Cron job with a Watchdog Script
Instead of forcing a refresh every hour (which might not be needed and creates unnecessary traffic), use a script that checks if the connection is actually broken and then forces a full restart (which triggers a fresh Solicit, fixing the "No Binding" loop).
Create a script `/root/ipv6_watchdog.sh`:
```bash
#!/bin/sh
# Check if we have a valid global IPv6 address on WAN6
# -w 2: wait 2 seconds
# -c 1: count 1
if ! ping6 -w 2 -c 1 ipv6.google.com %wan6 2>/dev/null; then
    # Ping failed, check if the log shows the specific error
    if logread -l 20 | grep -q "No Binding"; then
        logger "IPv6 Watchdog: 'No Binding' detected. Restarting wan6."
        # ifup triggers a full Solicit process, clearing the bad state
        ifup wan6
    fi
fi
```
*Note: If you don't have `ping6` or `ipv6.google.com` is blocked, you can change the check to `ip -6 route get 2000::/3`.*
Make it executable: `chmod +x /root/ipv6_watchdog.sh`
Add this to your crontab (checking every 5 or 10 minutes is better than hourly force-killing):
```cron
*/10 * * * * /root/ipv6_watchdog.sh
```
#### Step 3: Fix the Android Stale Address Issue
To force Android devices to give up the old IPv6 address when the prefix changes, you need to ensure the router advertises the *old* prefix as deprecated before switching to the new one. Since `odhcp6c` is crashing/restarting, it often forgets to do this.
1.  **Enable RA on deprecated prefixes**: In `/etc/config/dhcp`, ensure that old prefixes are still announced briefly with zero lifetime so clients know to drop them.
    Look for the `config odhcpd 'odhcpd'` section:
    ```config
    config odhcpd 'odhcpd'
        # ...
        option legacy '1'
    ```
    *If your OpenWrt version is recent, `odhcpd` handles this automatically IF the interface doesn't crash hard.*
2.  **The "Nuclear" Option for LAN (If Androids still stick)**:
    If the watchdog script from Step 2 triggers a restart, you can force a RA update on the LAN side.
    Modify the watchdog script:
    ```bash
    if ! ping6 -w 2 -c 1 ipv6.google.com %wan6 2>/dev/null; then
        if logread -l 20 | grep -q "No Binding"; then
            logger "IPv6 Watchdog: Restarting wan6 and lan dynamic dhcp"
            ifup wan6
            # Force odhcpd to re-advertise to LAN clients
            /etc/init.d/odhcpd restart
        fi
    fi
    ```
### Summary
1.  **The error "No Binding"** means your ISP forgot your lease. You cannot "Renew" (SIGUSR1) a forgotten lease; you must "Restart" (`ifup wan6`) to request a new one.
2.  **Fix the DUID** in `/etc/config/network` so the ISP recognizes you properly after restarts.
3.  **Use a watchdog script** that looks for "No Binding" and runs `ifup wan6`, rather than a timed `kill` command. This fixes the IPv6 connectivity.
4.  Restarting the WAN interface correctly (via `ifup`) usually triggers the proper RA updates on the LAN, causing Android devices to eventually drop the old IPs (usually within a minute or two).
