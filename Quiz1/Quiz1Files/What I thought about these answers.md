Actual situation:
There are some problems between my Openwrt router and the ISP. 
With the recommand config, the WAN6 interface has prefix renewing problem: It gets a new /128 IA_NA, a new /64 IA_NA, but no new /64 prefix.
Using `kill -SIGUSR1 $(pgrep odhcp6c)` fixes the /64 prefix renewing, but Android devices still have some problems with ipv6.



Positive things:
1. Some models realize there are 2 problems in the `INPUT.md`, while I hope the model to establish at least 2 different fix routines. One based on 'fixing desyncing between IA_NA and IA_PD on the WAN6 interface', and another one based on 'fixing that Android devices keep using old ipv6 addresses instead of using new ones'.
2. Some models pointed out using a hotplug triggered script is cleaner than using time-based cron command.
3. Some models think the input information is insufficient and ask back.
4. Some models recommand debug commands.



Negetive things:
1. Some models do not realize the `INPUT.md` contains 2 problems.
2. Some models have errors of markdown grammar.
3. Make up non-exist options of odhcp6c. (An official odhcp6c document `odhcp6c.html` is under the same path.)
4. Some models mixed the discription of IA_NA and IA_PD, then they thought there is no ipv6 prefix existing in abnormal conditions. In fact, there is a new /128 IA_NA, a new /64 IA_NA, and an old/broken /64 prefix on the WAN6 interface.
5. Some models ignore the details in the `INPUT.md`, which said 'restarting LAN could not make Android devices abandon the old ipv6 addresses', but some models still give the solutions of restarting LAN interface.
6. Assumption without evidence. Some models assumpt the router restarts before releasing, and give the 'DUID persistence fix' as the solution.
7. Misunderstanding of the need. I need usable GLA of LAN's downstream clients. Using ULA or disabling PD is a completely wrong solution.