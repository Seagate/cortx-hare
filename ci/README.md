# GitLab CI scripts

`.gitlab-ci.yml` [configures CI pipelines](https://docs.gitlab.com/ee/ci/yaml/).
To improve readability and maintainability of `.gitlab-ci.yml`, most
of the shell code from its `script:` sections has been moved to
scripts in `ci/` directory.

## Contexts of execution

- `ci/*` scripts run at GitLab runner's machine.
- `ci/docker/*` scripts run inside Docker container.
- `ci/m0vg/*` scripts run inside m0vg VM.
