---
domain: gitlab.mero.colo.seagate.com
shortname: 5/HAX
name: HA link eXtender
status: raw
editor: Valery V. Vorotyntsev <valery.vorotyntsev@seagate.com>
contributors:
  - Andriy Tkachuk <andriy.tkachuk@seagate.com>
  - Konstantin Nekrasov <konstantin.nekrasov@seagate.com>
---

## HA link eXtender (hax)

Mero process and Consul agent cannot communicate directly.  They communicate over `hax` server — a bridge, one side of which accepts connections from Mero processes, the other side communicates with Consul agent over HTTP.

![hax](hax.png)

The code of `hax` consists of C and Python parts.

* C part maintains HA link (`m0_ha_link`) connections with one or more `m0d` processes.  The code uses `m0_halon_interface` API.
* The callback functions passed to `m0_halon_interface_start()` are defined in the Python code.  Callback handlers (e.g., `entrypoint_request_cb`, `msg_received_cb`) send HTTP requests to Consul.
* Python part also runs HTTP server.  This server receives HTTP POST request from a Consul watch handler with payload of HA state updates.

## Is `m0_thread_adopt` necessary?

Mero functions - including FFI callbacks triggered by Mero - _may_ require that the threads they run on have thread-local storage (TLS) initialised in a specific way.  The threads managed by Python runtime do not meet this assumption, unless `hax` code makes `m0_thread_adopt` calls in proper places (`m0_thread_adopt` performs TLS initialisation as required by Mero).  The question is, whether Mero code executed by `hax` will actually _depend_ on Mero-specific TLS?  The most likely answer is “yes”.

### Some facts about Python threads

1. Threads created with [threading](https://docs.python.org/3/library/threading.html) API or with lower level [_thread](https://docs.python.org/3/library/_thread.html) API are not green threads.
2. Every time Python interpreter creates a thread on Linux platform, a new pthread (POSIX thread) is created.  Python thread never changes the underlying pthread.
3. The Python Global Interpreter Lock (GIL) is a mutex that allows only one thread to hold the control of the Python interpreter.  This means that only one thread can be in a state of execution at any point in time.

### Useful links

* `PyThread_start_new_thread` function ([source](https://github.com/python/cpython/blob/3.7/Python/thread_pthread.h#L179))
* [Coding patterns for Python extensions](https://pythonextensionpatterns.readthedocs.io/en/latest/)
