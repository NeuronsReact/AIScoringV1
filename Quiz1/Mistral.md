Thank you for sharing the details about your IPv6 issue. Let's try to understand and resolve this problem step by step.

First, could you please provide more information about your OpenWrt setup? Specifically:
1. What version of OpenWrt are you running?
2. Could you share the configuration of your WAN6 interface and any relevant DHCPv6 settings?
3. Are there any specific patterns or times when the issue occurs more frequently?

Additionally, the errors you're seeing (`No Binding` and `Not On Link`) suggest that the DHCPv6 server (on the ISP side) is having trouble maintaining the binding or is encountering link issues. The cron job you've set up to kill the odhcp6c process is a temporary workaround, but it's not ideal because it doesn't address the root cause and causes issues with your Android devices.

To better understand the issue, could you share more logs or any additional information about when and how often these errors occur? This will help us identify a more permanent solution.

In the meantime, you might want to look into adjusting the DHCPv6 client configuration in OpenWrt to handle these errors more gracefully. This could involve tweaking the renewal and rebind timers or investigating why the server is returning these errors.

Let's start with these questions and see if we can gather more information to diagnose the problem more accurately.