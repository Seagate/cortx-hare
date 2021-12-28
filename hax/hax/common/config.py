# Copyright (c) 2021 Seagate Technology LLC and/or its Affiliates
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# For any questions about this software or licensing,
# please email opensource@seagate.com or cortx-questions@seagate.com.
#
import hax.common as C
import hax.motr.workflow as W
import hax.motr.workflow.common as WC
import hax.queue.publish as P
import hax.util as U
import inject


def di_configuration(binder: inject.Binder):
    """
    Configures Dependency Injection (DI) engine.
    """
    binder.bind(C.HaxGlobalState, C.HaxGlobalState())

    cns_util = U.ConsulUtil()
    bq_publisher = P.BQPublisher(kv=cns_util.kv)
    binder.bind(U.ConsulUtil, cns_util)
    binder.bind(P.BQPublisher, bq_publisher)
    binder.bind(P.EQPublisher, P.EQPublisher(kv=cns_util.kv))

    helper = WC.ConsulHelper(cns=cns_util)
    executor = W.Executor(helper, bq_publisher)
    binder.bind(W.ObjectWorkflow, W.ObjectWorkflow(executor, helper))
