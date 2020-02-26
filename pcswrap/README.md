# Introduction

`pcswrap` package provides Python interface to Pacemaker's `pcs`
command-line utility.

The stack:
```
+--------+
|  hctl  | <-- invokes `pcswrap`; CLI utility
+--------+
| pcwrap | <-- calls `pcs` commands; Python module, CLI utility
+--------+
|  pcs   | <-- configures Pacemaker/Corosync; CLI utility
+--------+
```

# Try without installing Hare

```sh
cd pcswrap
pip3 install -r requirements.txt
sudo $(which python3)  # some `pcs` commands require superuser privileges
```

# Python API

Your main abstraction is `pcswrap.client.Client`.

Example:

```python
Python 3.6.8 (default, Aug  7 2019, 17:28:10)
[GCC 4.8.5 20150623 (Red Hat 4.8.5-39)] on linux
Type "help", "copyright", "credits" or "license" for more information.
>>> from pcswrap.client import Client
>>> c = Client()
>>> c.get_all_nodes()
[Node(name='ssc-vm-0018', online=True, shutdown=False, standby=False)]
>>> c.standby_node('ssc-vm-0018')
>>> c.get_all_nodes()
[Node(name='ssc-vm-0018', online=True, shutdown=False, standby=True)]
>>> c.standby_node('badname')
Traceback (most recent call last):
  File "<stdin>", line 1, in <module>
  File "/home/720599/projects/hare/pcswrap/pcswrap/client.py", line 30, in standby_node
    self.connector.standby_node(node_name)
  File "/home/720599/projects/hare/pcswrap/pcswrap/internal/connector.py", line 84, in standby_node
    self.executor.standby_node(node_name)
  File "/home/720599/projects/hare/pcswrap/pcswrap/internal/connector.py", line 19, in standby_node
    self._execute(['pcs', 'node', 'standby', node_name])
  File "/home/720599/projects/hare/pcswrap/pcswrap/internal/connector.py", line 43, in _execute
    raise CliException(out, err, exit_code)
pcswrap.exception.CliException: ('', "Error: Node 'badname' does not appear to exist in configuration\n", 1)
```

# Command-line interface

Use `pcswrap` executable.

```
$ pcswrap --help
usage: pcswrap [-h] {status,unstandby,standby,shutdown} ...

EOS HA Wrapper application. The application allows managing the nodes in HA
cluster.

positional arguments:
  {status,unstandby,standby,shutdown}
    status              Show status of all cluster nodes
    unstandby           Unstandby a node
    standby             Standby a node
    shutdown            Shutdown (power off) the node by name

optional arguments:
  -h, --help            show this help message and exit
```
