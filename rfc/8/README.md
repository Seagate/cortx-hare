---
domain: gitlab.mero.colo.seagate.com
shortname: 8/COSTY
name: Coding Style Guidelines
status: raw
editor: Valery V. Vorotyntsev <valery.vorotyntsev@seagate.com>
---

## Coding Style Guidelines

### Bash code

* Use 4 spaces for indentation.

* Start executable scripts with
  ```bash
  #!/usr/bin/env bash
  set -eu -o pipefail
  ```

* For the rest, follow
  [bahamas10's Bash Style Guide](https://github.com/bahamas10/bash-style-guide).

### Python code

* Use Python version 3.6.

* [flake8](https://pypi.org/project/flake8/) linter check should pass.

* [mypy](https://mypy.readthedocs.io/en/stable/) type check should pass.
  Type annotations are optional.

### C code

* Follow [Linux kernel coding style](https://www.kernel.org/doc/html/latest/process/coding-style.html).
