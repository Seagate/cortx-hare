---
domain: github.com
shortname: 12/CHECK
name: EES HA Health Checks
status: raw
editor: Maxim Medved <max.medved@seagate.com>
---

Some of the issues on the cluster could be detected by looking at systemd unit
states. Some of the issues can't. This is why we have EES HA Health Checks.

# EES HA Health Checks

## Overview

The primary goal of EES HA is to make EES data stack and EES management stack
highly available. To do this EES HA monitors system state and changes location
and/or configuration of services in case of hardware/software failures to run
them on the part of the system that hasn't failed. Basic error detection in
Pacemaker uses resource agent monitor operation. For systemd units it's just
monitoring unit state and if the systemd unit fails Pacemaker assumes that the
resource has failed an acts accordingly. Most of our services are systemd
services, so the only thing Pacemaker knows about them if their systemd unit is
active or not. This kind of monitoring doesn't cover situations when the
service itself is not functioning properly: it may be hung, deadlocked etc. If
a custom resource agent for our components does similar health check - like
"the process is running" - then it has the same issues as the systemd unit.

There is another issue with system monitoring: if EES HA starts watching for
all hardware and software components, it also needs to know exactly how are
they communicating and what are they depend on. Such dependencies are not
exactly the same as the startup/shutdown dependencies which Pacemaker uses to
start and stop the services, and without real communication dependencies
Pacemaker couldn't know when components are failing because of communication
issues. Adding communication dependencies into our current implementation is
not even close to an easy task.

To make EES HA to be able detect if components or entire data/management stack
are functioning a set of health checks was introduced. The purpose of health
checks is to be able to detect when a component or a set of components stop
functioning and then provide this information to EES HA, so EES HA can make a
decision about how to recover from this situation.

Health checks are implemented as checks of functionality. For one check this is
functionality of a single hardware component or network link, for another check
this is functionality of entire data stack.

## List of EES HA health checks

| implementation | integration | check-id | what it checks | how it checks | action if the check fails | components involved |
| -------------- | ----------- | -------- | -------------- | --------------| ------------------------- | ----------------------------------- |
| [EOS-4870](https://jts.seagate.com/browse/EOS-4870) | [EOS-4882](https://jts.seagate.com/browse/EOS-4882) | data1 | data stack on a single server | S3 request to HAProxy  | failover to the server where the test passes | Motr, S3 server |
| [EOS-4871](https://jts.seagate.com/browse/EOS-4871) | [EOS-4883](https://jts.seagate.com/browse/EOS-4883) | data2 | data stack on a both servers | S3 request to HAProxy  | run data1 on each server | Motr, S3 server |
| [EOS-4872](https://jts.seagate.com/browse/EOS-4872) | [EOS-4884](https://jts.seagate.com/browse/EOS-4884) | mgmt | management stack on a single server | ? | failover to another server | CSM |
| [EOS-4874](https://jts.seagate.com/browse/EOS-4874) | [EOS-4886](https://jts.seagate.com/browse/EOS-4886) | external-data | connection to the outside world over data network | ping default gw for data network | ? | - |
| [EOS-4875](https://jts.seagate.com/browse/EOS-4875) | [EOS-4887](https://jts.seagate.com/browse/EOS-4887) | external-mgmt | connection to the outside world over management network | ping default gw for management network | failover to another server if this ins the server where CSM is running | - |
| [EOS-4877](https://jts.seagate.com/browse/EOS-4877) | [EOS-4889](https://jts.seagate.com/browse/EOS-4889) | internal-data | network connectivity with other server over data network | ping other server over data network | run test on one server, failover to another server if it fails | - |
| [EOS-4878](https://jts.seagate.com/browse/EOS-4878) | [EOS-4890](https://jts.seagate.com/browse/EOS-4890) | internal-mgmt | network connectivity with other server over management network | ping other server over management network | run test on one server, failover to another server if it fails | - |
| [EOS-6586](https://jts.seagate.com/browse/EOS-6586) | [EOS-6587](https://jts.seagate.com/browse/EOS-6587) | cross-data | cross-server connection for data | ping other server over cross-server connection | choose one server, do failover | - |
| [EOS-4876](https://jts.seagate.com/browse/EOS-4876) | [EOS-4888](https://jts.seagate.com/browse/EOS-4888) | bmc | BMC availability over network | ipmitool power status | failover to the server where BMC works | - |
| [EOS-4873](https://jts.seagate.com/browse/EOS-4873) | [EOS-4885](https://jts.seagate.com/browse/EOS-4885) | saslink | SAS link | ? | ? | - |
| [EOS-4879](https://jts.seagate.com/browse/EOS-4879) | [EOS-4891](https://jts.seagate.com/browse/EOS-4891) | consul | Consul | get Consul leader | choose one server, do failover | Hare |
| [EOS-4880](https://jts.seagate.com/browse/EOS-4880) | [EOS-4892](https://jts.seagate.com/browse/EOS-4892) | sspl1 | SSPL end-to-end test on a single server	| ? | failover to another server | SSPL |
| [EOS-4881](https://jts.seagate.com/browse/EOS-4881) | [EOS-4893](https://jts.seagate.com/browse/EOS-4893) | sspl2 | SSPL end-to-end test on both servers | ? | ? | SSPL |
| [EOS-6588](https://jts.seagate.com/browse/EOS-6588) | [EOS-6589](https://jts.seagate.com/browse/EOS-6589) | uds | UDS service | ? | failover to another server | UDS |

## Integration

There are 2 options for health checks integration into Pacemaker:

1. Run health check in the resource agent monitor function. This would work if
   the component has a single custom resource agent. Example: if SSPL component
   has it's own resource agent the health check can be done as SSPL resource
   agent monitor function. This way SSPL resource agent will fail if SSPL stops
   functioning even if all SSPL processes are alive.
2. Make a special resource agent that can invoke health check function
   (resource agent defines resource type). Add resources with this type, then
   add dependencies on this resource with required failover logic. This might
   be required for checks with actions that depend on other checks. Example:
   data2 check needs data1 check to help with the decision.

## See also

* [Original list of EES HA health checks. The spreadsheet has a lot of useful information](https://docs.google.com/spreadsheets/d/1xASlPnlFx1OmhKttbgOweHbmfbXMI6n3Pmp2TSO8ou8/edit#gid=1305517710)
