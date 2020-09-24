# Contributing to Hare

Thank you for your interest in contributing to Hare!

## Process

This project uses [PC3 (Pedantic Code Construction Contract)](rfc/9/README.md)
process for contributions.

## Requesting changes

To request changes,
[log an issue](https://github.com/Seagate/cortx-hare/issues/new)
and describe the problem you are facing.

## Sending patches

0. [Fork](https://guides.github.com/activities/forking/) the repository
   (once).

1. Create a new branch.
   E.g.,
   ```sh
   git checkout -b save-the-prince
   ```

2. Implement the change, adhering to the
   [Coding Style Guidelines](rfc/8/README.md).

3. Prepare a commit in accordance with
   [Patch Requirements](rfc/9/README.md#22-patch-requirements).

   **Note:** use `git commit --signoff` to commit your code changes.
   You can enable `--signoff` by default with
   ```sh
   git config --local --add format.signOff true
   ```

4. [Create a pull request](https://docs.github.com/en/github/collaborating-with-issues-and-pull-requests/creating-a-pull-request-from-a-fork).

## See also

* [CORTX Contributing Guide](https://github.com/Seagate/cortx/blob/main/CONTRIBUTING.md)
