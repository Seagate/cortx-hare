---
domain: github.com
shortname: 22/MPAUX
name: Multipool Auxiliary Layout Parameters Generation
status: raw
editors: Suvrat Joshi <suvrat.joshi@seagate.com>
---

## Language

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://tools.ietf.org/html/rfc2119).

## Abstract

The multipools feature gives cluster an ability to have multiple pools (sets) of the disk/storage resources and IO's can be done on the desired pool.
The auxiliary pools feature is required for creating auxialiry pool sets, one of which could be used upon failure of one or more disk resources.

## Design


