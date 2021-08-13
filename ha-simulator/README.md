## Purpose

This folder contains the dockerized environment to debug and test HA Events. HA Events are sent by means of:

*   Kafka
*   MessageBus (wrapper for Kafka in cortx-py-utils)
*   Consul KV (used by cortx-ha to subscribe the components)
*   EventManager (cortx-ha).

The components above require additional configuration which is rather time-consuming.

Containerized environment helps to avoid configuration issues and concentrate on real coding instead.

## How to use

This section describes how this docker environment can be used.

### Pre-requisites

1.  Docker should be installed, see docs [here](https://docs.docker.com/get-docker/)

2.  docker-compose should be installed, see docs [here](https://docs.docker.com/compose/install/)

3.  cortx-ha (with EventManager support - see `fault_tolerance` branch) must be installed:

    *   either install the RPM from [here](http://cortx-storage.colo.seagate.com/releases/cortx/github/integration-custom-ci/centos-7.8.2003/custom-build-2434/cortx_iso/)

    *   or install cortx-ha into your virtualenv (this approach assumes that you run Hare from virtualenv environment, i.e. you had used `make devinstall`):

        1.  Activate Hare virtualenv: `source ./.py3venv/bin/activate`

        2.  Checkout cortx-ha sources: `git clone https://github.com/Seagate/cortx-ha.git`

        3.  `cd cortx-ha && git checkout fault_tolerance`

        4.  `python ./setup.py develop` - this will make sure that Hare virtualenv contains cortx-ha types and modules.

4.  Have local configuration files for MessageBus and HA are generated.

    *   Don't worry, just run `./prepare-host.sh` script.

### Get the environment

1.  Go to ha-simulator/ folder: `cd ha-simulator`

2.  Modify `./.env` file. CONSUL_HOSTNAME should point to the private IP address of your host machine. In other words, this is an IP address where Consul would respond (note that in Hare Consul is not listening to broad 0.0.0.0, usually it is bound to an address like 192.168.63.107 instead)

*   Normally, you can check this IP address like this:
    *   Setup the cluster with `hctl bootstrap cfgen/examples/singlenode.yaml`
    *   Run `consul members` to see the IP address.

3.  Run Kafka: `docker-compose up kafka`

4.  Run Hare cluster at your host machine: `hctl bootstrap <..>`

    *   If everything goes well, in journalctl logs from hax process there will be lines like these:

    <!---->

        2021-08-12 10:16:14,804 [INFO] {ha-event-listener} [subscribe] Received a subscribe request from hare
        2021-08-12 10:16:14,819 [INFO] {ha-event-listener} [__init__] MessageBus initialized as kafka
        2021-08-12 10:16:14,979 [INFO] {ha-event-listener} [subscribe] Successfully Subscribed component hare with message_type ha_event_hare

### Send simulated HA event

1.  Go to `ha-simulator/` folder

2.  Run `docker-compose up emitter`

    *   This container runs `./emitter.py` script. Feel free to edit it to send another events.

3.  Look into journalctl for new messages from `{ha-event-listener}` thread.
