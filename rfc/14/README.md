---
domain: gitlab.mero.colo.seagate.com
shortname: 14/HW
name: EES Hardware
status: raw
editor: Maksym Medvied <max.medved@seagate.com>
contributors:
  - Valery V. Vorotyntsev <valery.vorotyntsev@seagate.com>
---

## EES Hardware

| Component | Subcomponent | Number of units | Part of EES | Can lose power | Can be replaced after failure | SSPL Monitors | Is FRU? |
| --------- | ------------ | :-------------: | :---------: | :------------: | :---------------------------: | :-----------: | :-----: |
| TOR switch for data | | 1 | No | Yes | ? | No | ? |
| | Port | 2 | No | No | No | No | ? |
| | 50GbE cable | 2 | ? | No | Yes | No | ? |
| TOR switch for management | | 1 | No | Yes | ? | No | ? |
| | Port | 2 | No | No | No | No | ? |
| | Network cable | 2 | ? | No | Yes | No | ? |
| EES server | | 2 | Yes | Yes | Yes | No | ? |
| | CPU | 4 | Yes | Yes | No | No | No |
| | RAM | ? | Yes | Yes | No | No | No |
| | HDD | ? | Yes | Yes | Yes | ? | ? |
| | NIC for data | 2 | Yes | Yes | ? | No | No |
| | NIC for data: 50GbE port | 4 | Yes | No | ? | No | ? |
| | NIC for management | 2 | Yes | Yes | ? | No | No |
| | NIC for management: port | 2 | Yes | No | ? | No | ? |
| | Cross-server 50GbE cable | 1 | Yes | No | ? | ? | ? |
| | BMC | 2 | Yes | Yes | No | No | ? |
| | BMC network cable | ? | Yes | No | No | No | ? |
| | SAS HBA | 2 | Yes | Yes | No | No | No |
| | SAS x2 cable | 8 | Yes | No | No | No | ? |
| | PSUs | ? | ? | ? | ? | ? | ? |
| | Fans | ? | ? | ? | ? | ? | ? |
| 5U84 | Enclosure | 1 | Yes | Yes | No | Yes | ? |
| | Controller | 2 | Yes | Yes | Yes | Yes | ? |
| | Disk | 84 | Yes | Yes | Yes | Yes | ? |
| | Fan modules | 3 | Yes | Yes | Yes | Yes | ? |
| | PSUs | 2 | Yes | Yes | Yes | Yes | ? |
| | Sideplan expanders | 2 | Yes | Yes | Yes | Yes | ? |
| | SAS ports | 8 | Yes | ? | No | No | ? |

## See also

* "The New Direct-Connect Reference Architecture.." e-mail thread.
* [EOS HW HA Redux](https://seagatetechnology-my.sharepoint.com/:p:/g/personal/scott_hoot_seagate_com/EeznBp0URmRGjDI5fGQHtPYBtskEjjLHQPAEzjQdL-Fyag?e=kC2RHv) slides.
* "\[1103621-01\] EOS Exos Edge Store Appliance Build Instructions (5U84)" document.
