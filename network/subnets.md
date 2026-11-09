# Task 5: Subnetting and Network Access Control

## 1. Subnet allocation for 10.20.0.0/16

Rule: allocate the largest requirement first, start at 10.20.0.0, place each
subnet directly after the previous one, and use the smallest prefix whose
usable hosts (2^(32 - prefix) - 2) cover the requirement.

### Working

| Subnet     | Hosts needed | Smallest block that fits                                         | Prefix |
|------------|-------------:|------------------------------------------------------------------|-------:|
| app        | 1000         | 2^10 = 1024 addresses, 1022 usable (2^9 - 2 = 510 is too small)  | /22 |
| public     | 250          | 2^8 = 256 addresses, 254 usable (2^7 - 2 = 126 is too small)     | /24 |
| data       | 100          | 2^7 = 128 addresses, 126 usable (2^6 - 2 = 62 is too small)      | /25 |
| management | 20           | 2^5 = 32 addresses, 30 usable (2^4 - 2 = 14 is too small)        | /27 |

Placement (each block starts at the first address after the previous broadcast):

- app: starts at 10.20.0.0. 1024 addresses = 4 x 256, so it covers 10.20.0.0 - 10.20.3.255.
- public: next free address 10.20.4.0 (on a /24 boundary). 256 addresses: 10.20.4.0 - 10.20.4.255.
- data: next free address 10.20.5.0 (on a /25 boundary). 128 addresses: 10.20.5.0 - 10.20.5.127.
- management: next free address 10.20.5.128 (128 is a multiple of 32, so on a /27 boundary). 32 addresses: 10.20.5.128 - 10.20.5.159.

Network address = first address of the block, broadcast = last address,
usable range = network + 1 to broadcast - 1.

### Table

| Subnet     | Network address | Prefix | Usable host range         | Broadcast   | Usable hosts |
|------------|-----------------|-------:|---------------------------|-------------|-------------:|
| app        | 10.20.0.0       | /22    | 10.20.0.1 - 10.20.3.254   | 10.20.3.255 | 1022 |
| public     | 10.20.4.0       | /24    | 10.20.4.1 - 10.20.4.254   | 10.20.4.255 | 254  |
| data       | 10.20.5.0       | /25    | 10.20.5.1 - 10.20.5.126   | 10.20.5.127 | 126  |
| management | 10.20.5.128     | /27    | 10.20.5.129 - 10.20.5.158 | 10.20.5.159 | 30   |

Space used: 10.20.0.0 - 10.20.5.159. Everything from 10.20.5.160 to
10.20.255.255 stays free.

(Values cross-checked with Python's `ipaddress` module.)

## 2. NACL for the public subnet (`network/nacl.json`)

The load balancer lives in the public subnet (10.20.4.0/24). Clients use
ephemeral ports 1024-65535.

| Direction | Rule | Protocol | Port(s)    | CIDR            | Action | Purpose |
|-----------|-----:|----------|------------|-----------------|--------|---------|
| inbound   | 90   | all      | all        | 198.51.100.0/24 | deny   | Block the abusive range, even on web ports |
| inbound   | 100  | tcp      | 80         | 0.0.0.0/0       | allow  | HTTP from anywhere |
| inbound   | 110  | tcp      | 443        | 0.0.0.0/0       | allow  | HTTPS from anywhere |
| inbound   | 120  | tcp      | 22         | 10.20.5.128/27  | allow  | SSH only from the management subnet |
| inbound   | 130  | tcp      | 1024-65535 | 10.20.0.0/22    | allow  | Replies from the app subnet (to the LB's ephemeral port) |
| outbound  | 100  | tcp      | 8000       | 10.20.0.0/22    | allow  | LB forwards requests to the app on port 8000 |
| outbound  | 110  | tcp      | 1024-65535 | 0.0.0.0/0       | allow  | Replies back to clients' ephemeral ports |

A packet that matches no rule is denied (implicit default deny), so "nothing
else" needs no extra rule.

Check:

```
$ python tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check
 S01  inbound  tcp port 443   192.0.2.55      -> ALLOW (rule 110)  OK
 S02  inbound  tcp port 22    192.0.2.55      -> DENY  (no match (default deny))  OK
 S03  outbound tcp port 8000  10.20.1.1       -> ALLOW (rule 100)  OK
 S04  inbound  tcp port 443   198.51.100.9    -> DENY  (rule 90)  OK
 S05  outbound tcp port 60000 192.0.2.55      -> ALLOW (rule 110)  OK
 S06  inbound  tcp port 5432  10.20.5.20      -> DENY  (no match (default deny))  OK

Correct: 6 / 6 = 100.0%
```

## 3. Explanation

**Why a stateless NACL needs separate rules for reply traffic.** A NACL does
not remember connections. Every packet, replies included, is checked on its
own against the rules for its direction. When a client connects to the load
balancer on TCP 443, the request comes in on port 443, but the reply goes out
to the client's *ephemeral* port (1024-65535). The inbound "allow 443" rule
says nothing about that outbound packet. Without outbound rule 110 the reply
would hit the default deny and the client would never get an answer. The same
holds the other way: the load balancer opens connections to the app subnet on
port 8000 (outbound rule 100), and the app's replies return to the load
balancer's ephemeral port, which needs inbound rule 130. A stateful firewall,
such as a security group, would let these replies through automatically; a
NACL does not.

**Why rule order matters for 198.51.100.0/24.** Rules are checked from the
lowest number upward, and the first match decides. A packet from 198.51.100.9
to TCP 443 matches both the deny rule and "allow 443 from 0.0.0.0/0". The deny
only works if its number is lower than the allow rule it must override, so it
is rule 90, below the allows at 100 and up. Numbered 200 instead, rule 110
would match first and the abusive range would get in on the web ports.
