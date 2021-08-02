# Hare Code Coverage User Guide

## Steps to generate code coverage

1.  Clone [Hare](https://github.com/Seagate/cortx-hare) repository.

2.  Navigate to hare home directory using `cd hare`.

3.  Build Hare code - `cd hare && make install`.

4.  Activate the virtual environment using `source .py3venv/bin/activate`.

5.  Run the `hare_coverage.py`. It will generate the `xml` report inside 
    `hare_coverage_report/coverage.xml`.

<!------------------------------------------------------------------->
## Wrapper script to run coverage executable. 
`generate_coverage` script present inside `utils` which will activate virtual environment
and run `hare_coverage.py` script. Apart from that this script export hare base directory
`opt/seagate/cortx/hare`'s `site-packages` path to PYTHONPATH and `bin` to PATH as this
exports are not done with `make install`.
NOTE: The wrapper script wont work when Hare is installed from RPM.
### `generate-coverage` execution snippet:
```
    (.py3venv) [root@ssc-vm-5917 hare_repo]# python hare/utils/hare_cov/hare_coverage.py
    2021-08-24 04:02:19,796 [INFO] Verify the logs at '/root/hare_repo/coverage.log'.
    2021-08-24 04:02:19,796 [INFO] Running Python Coverage Tool.
    2021-08-24 04:02:19,796 [INFO] Cleaning up the report.
    2021-08-24 04:02:19,799 [INFO] Running unit tests.
    2021-08-24 04:02:21,017 [INFO] Testcase Results:
    ============================= test session starts ==============================
    platform linux -- Python 3.6.8, pytest-6.2.4, py-1.10.0, pluggy-0.13.1
    rootdir: /root/hare_repo/hare/provisioning/miniprov
    plugins: cov-2.12.1, timeout-1.4.2, mock-3.6.1, aiohttp-0.3.0
    collected 23 items
    
    hare/provisioning/miniprov/test/test_cdf.py ..................           [ 78%]
    hare/provisioning/miniprov/test/test_systemd.py ...                      [ 91%]
    hare/provisioning/miniprov/test/test_validator.py ..                     [100%]
    
    ============================== 23 passed in 0.50s ==============================
    
    2021-08-24 04:02:46,231 [INFO] Testcase Results:
    ============================= test session starts ==============================
    platform linux -- Python 3.6.8, pytest-6.2.4, py-1.10.0, pluggy-0.13.1
    rootdir: /root/hare_repo/hare/hax
    plugins: cov-2.12.1, timeout-1.4.2, mock-3.6.1, aiohttp-0.3.0
    collected 30 items
    
    hare/hax/test/test_delivery_herald.py .............                      [ 43%]
    hare/hax/test/test_offset_storage.py ..                                  [ 50%]
    hare/hax/test/test_work_planner.py .........                             [ 80%]
    hare/hax/test/integration/test_motr.py .                                 [ 83%]
    hare/hax/test/integration/test_server.py .....                           [100%]
    
    ============================= 30 passed in 24.52s ==============================
    
    2021-08-24 04:02:46,232 [INFO] Running Coverage.
    2021-08-24 04:03:13,747 [INFO] Verify report.
    2021-08-24 04:03:13,747 [INFO] Python Code Coverage Report generated successfully at '/root/hare_repo/hare/hare_coverage_report/coverage.xml'.
    2021-08-24 04:03:14,137 [INFO] Python Coverage report:
    Name                                                       Stmts   Miss  Cover
    ------------------------------------------------------------------------------
    hare/hax/hax/__init__.py                                       0      0   100%
    hare/hax/hax/exception.py                                     16      2    88%
    hare/hax/hax/filestats.py                                     53     53     0%
    hare/hax/hax/handler.py                                      133     69    48%
    hare/hax/hax/hax.py                                           72     72     0%
    hare/hax/hax/log.py                                           14      0   100%
    hare/hax/hax/message.py                                       77      0   100%
    hare/hax/hax/motr/__init__.py                                298    160    46%
    hare/hax/hax/motr/delivery.py                                 98      9    91%
    hare/hax/hax/motr/ffi.py                                      84     68    19%
    hare/hax/hax/motr/planner.py                                 135     18    87%
    hare/hax/hax/motr/rconfc.py                                   38     38     0%
    hare/hax/hax/motr/util.py                                     54      7    87%
    hare/hax/hax/queue/__init__.py                                64     25    61%
    hare/hax/hax/queue/cli.py                                     32     32     0%
    hare/hax/hax/queue/confobjutil.py                              7      1    86%
    hare/hax/hax/queue/offset.py                                  42      0   100%
    hare/hax/hax/queue/publish.py                                 29     12    59%
    hare/hax/hax/server.py                                       127     46    64%
    hare/hax/hax/types.py                                        126     15    88%
    hare/hax/hax/util.py                                         581    403    31%
    hare/provisioning/miniprov/hare_mp/__init__.py                 0      0   100%
    hare/provisioning/miniprov/hare_mp/cdf.py                    171      7    96%
    hare/provisioning/miniprov/hare_mp/dhall/__init__.py           0      0   100%
    hare/provisioning/miniprov/hare_mp/main.py                   395    395     0%
    hare/provisioning/miniprov/hare_mp/store.py                   54     11    80%
    hare/provisioning/miniprov/hare_mp/systemd.py                 12      0   100%
    hare/provisioning/miniprov/hare_mp/templates/__init__.py       0      0   100%
    hare/provisioning/miniprov/hare_mp/types.py                  109      2    98%
    hare/provisioning/miniprov/hare_mp/validator.py               27      6    78%
    ------------------------------------------------------------------------------
    TOTAL                                                       2848   1451    49%
```
