---
domain: github.com
shortname: 16/RCE
name: Recovery Coordination Engine
status: raw
editor: Valery V. Vorotyntsev <valery.vorotyntsev@seagate.com>
---

Keywords: BQ, EQ, RC, event, rule

<!-- XXX
  -- Keywords: EQ, BQ, RC, timers
  --
  -- Note: event types and rules (and rules' effects) will be specified in a separate RFC.
  -->

<!-- XXX TODO:
  --
  -- * Logging & observability.
  --
  -- * Add new terms to 10/GLOSS.
  --
  -- * Timers mechanism.
  --
  -- * "BQ-delivered" (a.k.a. BQ acks) mechanism.
  --
  -- * How to ensure that only RC can modify the BQ?
  --   See
  --   1. [ACL System](https://www.consul.io/docs/acl/acl-system)
  --   2. [Bootstrap the ACL system](https://learn.hashicorp.com/tutorials/consul/access-control-setup-production)
  --   3. [ACL Rules](https://www.consul.io/docs/acl/acl-rules)
  --
  -- * Read about Consul [Security Model](https://www.consul.io/docs/internals/security.html).  How can we apply that information?
  -->

## Language

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://tools.ietf.org/html/rfc2119).

## Implementation

### Prerequisites

* Consul KV store MUST have `eq/` and `bq` key prefix.

* Hare software package MUST provide `h0q` CLI utility.  Users SHOULD use this utility to put entries into EQ and BQ.

  Usage:
  ```sh
  CONSUL_ACL_TOKEN=<eq-write-token> h0q <key-prefix> <value>
  ```

### Event Queue (EQ)

The EQ is the queue of incoming _events_ that outside entities (e.g., Motr, HA, human operator) want Hare RC to know about.

The EQ is represented by Consul KV entries with `eq/` prefix.

<!-- XXX Describe epoch? -->

Adding event to the EQ:
```sh
CONSUL_ACL_TOKEN=<eq-write-token> hoq eq \
    '{ "type": "<event-type>", "payload": "<event-payload>" }'
```

Supported event types and their payload are specified in [19/EVERULES](../19/README.md).

### Recovery Coordinator (RC)

1. On the Consul leader node there MUST be configured a [watch](https://www.consul.io/docs/agent/watches.html#keyprefix) of "keyprefix" type that watches `eq/` key prefix.  Whenever the EQ is modified, the handler of this watch will execute the _RC_ and pass it full contents of the EQ in JSON format via stdin.

1. There MUST NOT be several simultaneously running RC instances.  <!-- XXX This is guaranteed by Consul, isn't it? -->

1. The RC MUST process all the events in the EQ.

1. To process an event, the RC finds the _rule_ associated with this event type and executes it.

   1. Rules are executable files.

   1. Rules MUST obtain event payload from the standard input.

   1. Rules SHOULD have _effects_.  E.g.: put an item into the BQ/EQ, add new entry to the system log, execute a shell command.

   Supported rules and their effects are specified in [19/EVERULES](../19/README.md).

1. It is RECOMMENDED to define a special `_default` rule.  The RC SHALL apply the `_default` rule if there is no rule associated with the type of processed event.

<!-- XXX We may borrow some rule processing ideas from iptables/nftables.
  -->

1. The RC MUST abort a rule that runs longer than predetermined \<timeout\>.
1. If rule terminates with nonzero exit code, the RC SHALL log this error in the systemd log.

<!-- XXX How is RC to be configured?  Do we want to reconfigure it at runtime?
  -->

1. The same set of rules MUST be installed in the same directory on every Consul server node.

   E.g., a directory of rules that handle events of types "foo", "bar", and "baz" would look like this:
  ```sh
  rules/
   \_ _default
   \_ bar
   \_ baz
   \_ foo
  ```

1. The RC and rules SHOULD take configuration parameters from environment variables and SHOULD NOT use command line options.  <!-- Rationale: https://12factor.net/config -->

1. The RC MUST delete processed events from the EQ.

### Broadcast Queue (BQ)

The BQ is the queue of outgoing _messages_ that Hare RC wants to be delivered to all Motr processes.

The BQ is represented by Consul KV entries with `bq/` prefix.

Adding message to the BQ:
```sh
CONSUL_ACL_TOKEN=<bq-write-token> hoq bq <message>
```

<!-- XXX-OPTIMIZATION: `h0q` uses Consul transaction mechanism and CAS to increment the epoch.  If only RC is allowed to modify the BQ, we may want to use a more lightweight mechanism. -->

* Only RC SHOULD be able to modify the BQ.  <!-- XXX How to ensure that? -->

* For every Consul node there MUST be configured a watch of "keyprefix" type that watches `bq/` key prefix.  Whenever the BQ is modified, these watches will send full contents of the BQ in JSON format to local Hax processes over HTTP.

## Examples of Fault Handling

![cluster-faults](cluster-faults.png)

### 1. Disk failure

* Detected by Motr IOS when it tries to perform I/O operation.
* The IOS sends M0_HA_MSG_STOB_IOQ message to the local Hax.
* Hax puts an event into the EQ.  This triggers the RC.
* The RC applies the corresponding rule.
* The rule puts a message into the BQ.
* Consul BQ watch handlers send HTTP request with watch invocation
  data (contents of the BQ) to all Haxes.
* Upon receiving the request, each of the Haxes send the notification
  (M0_HA_MSG_NVEC) to the connected Motr processes.

<!-- XXX-TODO: Add a [sequence diagram](https://plantuml.com/sequence-diagram).
  -->
