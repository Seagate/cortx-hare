---
domain: gitlab.mero.colo.seagate.com
shortname: 5/HAX
name: HA link eXtender
status: raw
editor: Valery V. Vorotyntsev <valery.vorotyntsev@seagate.com>
contributors:
<<<<<<< HEAD
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

## Notes on Python threading model

When being invoked, Mero calls have special assumptions on the threads they are currently on. The key point is that the Mero's local thread storage (LTS)  must be properly initialized beforehand. That's why it is pretty important to understand the connection between Pythonic threads and the OS-level threads Mero is aware of.

### Some facts on Python threads
1. The threads one creates with `threading` (and thus with `_thread` module) are not the green ones.
2. Every time the Python program creates a thread, a new pthread is created (in case of Linux, of course).
3. Although Python interpreter switches the thread activity by means of GIL (Global Interpreter Lock), the Python thread never changes its underlying pthread.
4. The facts above don't apply to async/await mechanism and to libraries like `greenlet`.

### Useful links and materials
1. PyThread_start_new_thread function [source](https://github.com/python/cpython/blob/3.7/Python/thread_pthread.h#L179)
2. [Coding patterns for Python extensions](https://pythonextensionpatterns.readthedocs.io/en/latest/)

