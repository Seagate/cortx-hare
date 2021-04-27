---
domain: github.com
shortname: 20/MINIPROV
name: Mini-Provisioning API Support
status: draft
editor: Konstantin Nekrasov <konstantin.nekrasov@seagate.com>
---

<!-- vim-markdown-toc GFM -->

* [Language](#language)
* [Abstract](#abstract)
* [Vocabulary](#vocabulary)
* [General setup.yaml structure](#general-setupyaml-structure)
  * [Notes](#notes)
  * [Stage conditions](#stage-conditions)
* [Communication with ConfStore](#communication-with-confstore)
* [Proposed changes to Hare](#proposed-changes-to-hare)
  * [Stage implementations](#stage-implementations)
    * [post_install](#post_install)
    * [config](#config)
      * [CDF generation](#cdf-generation)
    * [init](#init)
    * [test](#test)

<!-- vim-markdown-toc -->

## Language

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://tools.ietf.org/html/rfc2119).

## Abstract

Hare component must implement Mini-Provisioner API (see the [specification document](https://seagatetechnology.sharepoint.com/:w:/r/sites/gteamdrv1/tdrive1224/_layouts/15/guestaccess.aspx?email=nitin.nimran%40seagate.com&e=4%3ADCGSG0&at=9&CID=C40F4AE6-CD62-43A6-8B09-A76C04A292F1&wdLOR=cA34642E5-B304-413A-BED3-2FD178DACFDF&share=Ea2OBEFIPmNBucxpoE_n5nsB126Vr3sA_-KY-4_hHYkNVA) for more details). In a nutshell Hare must have scripts that setup a singlenode cluster using [ConfStore](https://seagatetechnology.sharepoint.com/:w:/r/sites/gteamdrv1/tdrive1224/_layouts/15/Doc.aspx?sourcedoc=%7BA68B2DB0-B041-4136-8F51-94F0A4685D1E%7D&file=ConfStore_Specification.docx&action=default&mobileredirect=true) as a source of configuration parameters and publish those scripts via a `setup.yaml` file of a predefined format.

## Vocabulary

1. Mini-Provisioner API - a part of CORTX V2 Provisioner Framework. CORTX Provisioner defines Mini-Provisioner API interfaces to support phase-wise installation for each of the components which is specified using standard template: `/opt/seagate/cortx/<component>/conf/setup.yaml`
2. ConfStore - a [lens-like thing](https://medium.com/@russmatney/haskell-lens-operator-onboarding-a235481e8fac) (yes, almost in the sense of Haskell) to work with various file formats and potentially databases as if it is a Key-Value storage. The idea is that different components may require similar knowledge about the cluster configuration or produce some knowledge that can be used later by another components during their self-deployment. So it is natural that at the level of Provisioner Framework we have a shared "database" to store and exchange the facts. But instead of the "database" we're given with an optics to it.

## General setup.yaml structure

```yaml
    <component>:   
      post_install:  				# Example: 
        cmd: <script path>			# Script provided by Component
        args: --config $URL			# ConfStore Config URL provided by Provisioner 
      config:  			 
        cmd: csm_setup				# Example: 
        args: --cmd config			# Command and Args provided by Component
      init:   
        cmd: <script path> 
        args: --config $URL 
      test:   
        cmd: <script path> 
        args: --config $URL [--plan]		# Perform plan specific tests
      upgrade:   
        cmd: <script path> 
        args: --config $URL 
      reset:  					# Remove logs and meta-data (accounts) 
        cmd: <script path> 			# Delete test related data 
        args: --config $URL			 
      cleanup:              			# Remove specific configuration (schema) 
        cmd: <script path>                      # Delete config related data 
        args: --config $URL 
      backup: 					# URL provided by Component 
        cmd: <script path> 
        target: <URL>     			# Custom end-point to backup config (Consul) 
      restore: 
        cmd: <script path> 
        target: <URL>           		# Custom end-point for restoring config (Consul) 
      support_bundle:   
        - /opt/seagate/cortx/provisioner/cli/provisioner-bundler   
```

### Notes

1. The given yaml file structure is not final (source: meeting with Nitin Nimran, Mandar Sawant and Ujjwal Lanjewar, "ConfStore Q&A" 01/18/21).
2. There are neither specific guarantees nor assumptions on what the scripts must do and in which state they leave the system. Reason: Mini Framework is not supposed to be integrated well with Provisioner Framework, hence no responsibility and no clear contracts (source: meeting with Nitin Nimran, Mandar Sawant and Ujjwal Lanjewar, "ConfStore Q&A" 01/18/21).
3. Most of the stages can be no-op (source: meeting with Nitin Nimran, Mandar Sawant and Ujjwal Lanjewar, "ConfStore Q&A" 01/18/21).
4. `<component>` is an arbitrary name. Hare team is free to choose any name (e.g. 'hare', 'Hare' or 'cortx-hare').
5. `<URL>` is a placeholder (macro) that will be replaced with a real URL automatically by the external tool that execute the scripts from the yaml file.
6. Every stage must be idempotent. If the stage is applied twice in a row, the second run must succeed also. Effectively there must be no difference if the stage is applied once or N times in a row.
7. Every stage is executed with root permissions.
8. Scripts must use exit codes: 0 in case of SUCCESS, a number N > 0 if an ERROR occured.


### Stage conditions

| Stage        | Purpose           | Expected initial state  | Side effects performed as a result |
| ------------- |-------------| ----- | --- |
| [post_install](#post_install)  | Verify that all the required 3rd party components are installed and have correct versions (Optional?) | Component RPM has just been installed to the OS. No services are started. | None (stage either fails or succeeds) |
| [config](#config)  | Apply changes to the OS to satisfy the needs of our component | Same to post_install | OS-level settings satisfy the needs of the component. |
| [init](#init)  | Initialize and start the component. | OS is ready to launch the component. | The component is started. |
| [test](#test)  | Sanity tests ran against the running component. The tests can produce some logs but they must not damage end user's data (reason: this stage can be executed in the field as well). | The component is started. | The component is started. The component looks working (no critical problems with the functionality were identified). |
| [reset](#reset)  | Removes logs and other artifacts of test stage. | Makes no assumption on the component status. | Makes no assumption on the component status. |
| [cleanup](#cleanup)  | Cleans the component-specific configuration. | TBD | The component is stopped, the configuration is cleared out. |
| [upgrade](#upgrade)  | Perform the upgrade of the component (3rd-party components included). | TBD | TBD |
| [backup](#backup)  | Save and export component's state so that it is state can be reproduced at another machine (TBD is it feasible?) | TBD | TBD |
| [restore](#restore)  | An action opposite to `backup`. Must ingest the exported backup and apply it. | TBD | TBD |
| [support_bundle](#support_bundle)  | Generates support bundle using `hare_setup support_bundle` command | Destination directory must be writable | None (bundle generation may pass or fail) |


## Communication with ConfStore

TBD

## Proposed changes to Hare

1. All commands will be handled by `provisioning/setup.py` file.
2. `provisioning/setup.py` must be renamed to `provisioning/setup_hare` (the file must be executable so proper shebang must be added to the first line).
3. `setup_hare` must provide help screen (i.e. it must show help information when `-h` or `--help` flag is provided).

### Stage implementations

#### post_install
```
/opt/seagate/cortx/hare/bin/hare_setup post_install --config 'json:///tmp/exampleV2.json'
```
Verifies that
1. Motr, Hare, Consul rpms are installed.
2. Consul binary has a version that Hare supports (1.7.8 at the moment - TBD clarify)

Exit codes: 0 if no issues found, 1 otherwise.

#### config
```
/opt/seagate/cortx/hare/bin/hare_setup config --config 'json:///tmp/exampleV2.json' --file '/var/lib/hare/cluster.yaml'
```
1. Generates CDF file according to the configuration provided by <str> (URL) parameter.
2. Applies configuration to Consul.

Exit codes: 0 if no issues found, 1 otherwise.

##### CDF generation

**Assumptions**
1. ConfStore contains information about one node only. In other words, `cluster>server_nodes` contains a dictionary with one element only - that node is the current one where Mini Provisioner is invoked.
2. `cluster>{$server-node}>network>data>interfaces` contains a list of values while CDF takes one value only. The first item in the list will be used.

**Parameters consumed from ConfStore for CDF generation**

| Parameter       | Key in ConfStore                                 | Comment                                                                                           |
|-----------------|--------------------------------------------------|---------------------------------------------------------------------------------------------------|
| hostname        | `cluster>{$server-node}>hostname`                | Correct `$server-node` must be taken initially from `cluster>server_nodes`                        |
| data_iface      | `cluster>{$server-node}>network>data>interfaces` | This is actually a comma-separated list of strings. The first iface will be taken from that list. |
| io_disks        | `cluster>{$server-node}>storage>data_devices`    |                                                                                                   |
| data_iface_type | `cluster>{$server-node}>network>data>interface_type` | Data interface type (tcp|o2ib)                                                                |
| s3_client_count | `cluster>{$server-node}>s3_instances`            | No of s3 server instances                                                                         |

#### init
```
/opt/seagate/cortx/hare/bin/hare_setup init --config 'json:///tmp/exampleV2.json'
```
1. Invokes 'hctl bootstrap --mkfs'(If cluster is not already running)

2. Invokes 'hctl shutdown'

Exit codes: 0 if no issues found (so Hare cluster running), 1 otherwise.

#### test
```
/opt/seagate/cortx/hare/bin/hare_setup test --config 'json:///tmp/exampleV2.json'
```
Run functional tests against a running singlenode cluster (TBD).
Runs 'hctl status --json' and compares output with info extracted from CDF used during bootstrap to check if all the services are running correctly.

### support bundle

```
[root@ssc-vm-1623:root] /opt/seagate/cortx/hare/bin/hare_setup support_bundle
[root@ssc-vm-1623:root] ls /tmp/hare
hare_ssc-vm-1623.tar.gz
[root@ssc-vm-1623:root] /opt/seagate/cortx/hare/bin/hare_setup support_bundle SB12345 /root
[root@ssc-vm-1623:root] ls hare
hare_SB12345.tar.gz
```
