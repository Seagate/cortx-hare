---
domain: gitlab.mero.colo.seagate.com
shortname: 8/STYLE
name: Coding Style Guidelines
status: draft
editor: Valery V. Vorotyntsev <valery.vorotyntsev@seagate.com>
---

## Coding Style Guidelines

* All error messages should go to stderr.

### Bash code

* Use 4 spaces for indentation.

* Executable scripts should start with
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

* Executable scripts should start with
  ```python
  #!/usr/bin/env python3
  ```

### C code

* Follow [Linux kernel coding style](https://www.kernel.org/doc/html/latest/process/coding-style.html).

<!-- XXX Editor settings
Consider using https://editorconfig.org
-->
