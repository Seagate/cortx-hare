/* -*- C -*- */
/*
 * COPYRIGHT 2019 SEAGATE TECHNOLOGY LIMITED
 *
 * THIS DRAWING/DOCUMENT, ITS SPECIFICATIONS, AND THE DATA CONTAINED
 * HEREIN, ARE THE EXCLUSIVE PROPERTY OF SEAGATE TECHNOLOGY
 * LIMITED, ISSUED IN STRICT CONFIDENCE AND SHALL NOT, WITHOUT
 * THE PRIOR WRITTEN PERMISSION OF SEAGATE TECHNOLOGY LIMITED,
 * BE REPRODUCED, COPIED, OR DISCLOSED TO A THIRD PARTY, OR
 * USED FOR ANY PURPOSE WHATSOEVER, OR STORED IN A RETRIEVAL SYSTEM
 * EXCEPT AS ALLOWED BY THE TERMS OF SEAGATE LICENSES AND AGREEMENTS.
 *
 * YOU SHOULD HAVE RECEIVED A COPY OF SEAGATE'S LICENSE ALONG WITH
 * THIS RELEASE. IF NOT PLEASE CONTACT A SEAGATE REPRESENTATIVE
 * https://www.seagate.com/contacts
 *
 * Original author: Konstantin Nekrasov <konstantin.nekrasov@seagate.com>
 *		    Mandar Sawant <mandar.sawant@seagate.com>
 * Original creation date: 10-Jul-2019
 */

#include <Python.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include "fid/fid.h"             /* M0_FID_TINIT */
#include "ha/halon/interface.h"  /* m0_halon_interface */
#include "ha/note.h"
#include "module/instance.h"
#include "lib/assert.h"          /* M0_ASSERT */
#include "lib/memory.h"          /* M0_ALLOC_ARR */
#include "lib/thread.h"          /* m0_thread_{adopt, shun} */
#include "lib/string.h"          /* m0_strdup */
#include "lib/trace.h"           /* M0_LOG, M0_DEBUG */
#include "mero/version.h"        /* M0_VERSION_GIT_REV_ID */
#include "ha/msg.h"
#include "hax.h"

static struct hax_context *hc;

// XXX Shouldn't these be `static`?
struct m0_thread    m0thread;
struct m0          *m0;

static void _ha_test_entrypoint_reply_send(struct m0_halon_interface *hi,
                                           const struct m0_uint128   *req_id,
                                           const char                *remote_rpc_endpoint,
                                           const struct m0_fid       *process_fid,
                                           const char                *git_rev_id,
                                           uint64_t                   pid,
                                           bool                       first_request);
static void __ha_failvec_reply_send(const struct hax_msg *hm,
				    struct m0_fid *pool_fid,
                                    uint32_t nr_notes);
static void nvec_test_reply_send(const struct hax_msg *hm);
static void __ha_nvec_reply_send(const struct hax_msg *hm,
				 struct m0_ha_nvec *nvec);

PyObject* getModule(char *module_name)
{
	PyObject *sys_mod_dict = PyImport_GetModuleDict();
	PyObject *hax_mod = PyMapping_GetItemString(sys_mod_dict, module_name);
	if (hax_mod == NULL) {
		PyObject *sys = PyImport_ImportModule("sys");
		PyObject *path = PyObject_GetAttrString(sys, "path");
		PyList_Append(path, PyUnicode_FromString("."));

		Py_DECREF(sys);
		Py_DECREF(path);

		PyObject *mod_name = PyUnicode_FromString(module_name);
		hax_mod = PyImport_Import(mod_name);
		Py_DECREF(mod_name);
	}
	return hax_mod;
}

PyObject *toFid(const struct m0_fid *fid)
{
	PyObject *hax_mod = getModule("hax.types");
	PyObject *instance = PyObject_CallMethod(hax_mod, "Fid", "(KK)",
						 fid->f_container, fid->f_key);
	Py_DECREF(hax_mod);
	return instance;
}

PyObject *toUid128(const struct m0_uint128 *val)
{
	PyObject *hax_mod = getModule("hax.types");
	PyObject *instance = PyObject_CallMethod(hax_mod, "Uint128", "(KK)",
						 val->u_hi, val->u_lo);
	Py_DECREF(hax_mod);
	return instance;
}

static void entrypoint_request_cb(struct m0_halon_interface *hi,
				  const struct m0_uint128 *req_id,
				  const char *remote_rpc_endpoint,
				  const struct m0_fid *process_fid,
				  const char *git_rev_id,
				  uint64_t pid,
				  bool first_request)
{
	struct hax_entrypoint_request *ep;

	/*
	 * XXX This is obligatory since we want to work with Python object
	 * and we obviously work from an external thread.
	 * FYI: https://docs.python.org/2/c-api/init.html#releasing-the-gil-from-extension-code
	 */
	PyGILState_STATE gstate;
	gstate = PyGILState_Ensure();

	M0_ALLOC_PTR(ep);
	M0_ASSERT(ep != NULL);
	ep->hep_hc = hc;

	M0_LOG(M0_INFO, "In entrypoint_request_cb\n");
	PyObject *py_fid = toFid(process_fid);
	PyObject *py_req = toUid128(req_id);

	/*
	 * XXX The magic syntax of (KOsOsKb) is explained here:
	 * https://docs.python.org/3.7/c-api/arg.html#numbers
	 *
	 * Note that `K` stands for `unsigned long long` while `k` is simply
	 * `unsigned long` (be aware of overflow).
	 */
	PyObject_CallMethod(hc->hc_handler, "_entrypoint_request_cb",
			    "(KOsOsKb)", ep, py_req, remote_rpc_endpoint,
			    py_fid, git_rev_id, pid, first_request);
	Py_DECREF(py_req);
	Py_DECREF(py_fid);
	// XXX Note that the Python threads get unblocked only after this call.
	PyGILState_Release(gstate);
  }

static void _ha_test_entrypoint_reply_send(struct m0_halon_interface *hi,
					   const struct m0_uint128   *req_id,
					   const char                *remote_rpc_endpoint,
					   const struct m0_fid       *process_fid,
					   const char                *git_rev_id,
					   uint64_t                   pid,
					   bool                       first_request)
{
	struct m0_fid *confd_fids;
	const char   **confd_eps;
	const char    *rm_ep;

	/* XXX TODO: Move test code to separate location.*/

	M0_ALLOC_ARR(confd_fids, 1);
	M0_ASSERT(confd_fids != NULL);
	confd_fids[0] = M0_FID_TINIT('s', 3, 1);

	M0_ALLOC_ARR(confd_eps, 1);
	M0_ASSERT(confd_eps != NULL);
	confd_eps[0] = m0_strdup("172.28.128.4@tcp:12345:44:1");
	M0_ASSERT(confd_eps[0] != NULL);

	rm_ep = m0_strdup("172.28.128.4@tcp:12345:44:1");
	M0_ASSERT(rm_ep != NULL);

	m0_halon_interface_entrypoint_reply(hi, req_id, 0, 1, confd_fids,
					    confd_eps, 1,
					    &M0_FID_TINIT('s', 4, 1), rm_ep);
	M0_LOG(M0_ALWAYS, "Entry point replied");

	m0_free(confd_fids);
	m0_free(confd_eps);
}

/*
 * To be invoked from python land.
 */
M0_INTERNAL void m0_ha_entrypoint_reply_send(unsigned long long        epr,
					     const struct m0_uint128  *req_id,
					     int                       rc,
					     uint32_t                  confd_nr,
					     const struct m0_fid      *confd_fid_data,
					     const char              **confd_eps_data,
					     uint32_t                  confd_quorum,
					     const struct m0_fid      *rm_fid,
					     const char               *rm_eps)
{
	struct hax_entrypoint_request *hep = (struct hax_entrypoint_request *)epr;

	m0_halon_interface_entrypoint_reply(hep->hep_hc->hc_hi, req_id, rc,
					    confd_nr, confd_fid_data,
					    confd_eps_data, confd_quorum,
					    rm_fid, rm_eps);
	m0_free(hep);
}

static void handle_failvec(const struct hax_msg *hm)
{
	M0_PRE(hm != NULL);
	/*
	 * Invoke python call from here, comment the mock reply send and pass
	 * hax_msg (hm).
	 *
	 * XXX TODO: Move test calls to a separate location.
	 */
	__ha_failvec_reply_send(hm, &M0_FID_TINIT('o', 2, 9), 0);
}

/*
 * Sends failvec reply.
 * To be invoked from Python land.
 */
M0_INTERNAL void m0_ha_failvec_reply_send(unsigned long long hm,
					  struct m0_fid *pool_fid,
					  uint32_t nr_notes)
{
	M0_PRE(hm != NULL);
	__ha_failvec_reply_send((struct hax_msg *)hm, pool_fid, nr_notes);
}

static void __ha_failvec_reply_send(const struct hax_msg *hm,
				    struct m0_fid *pool_fid,
				    uint32_t nr_notes)
{
	struct m0_ha_link *hl = hm->hm_hl;
	struct m0_ha_msg  *msg = hm->hm_msg;
	struct m0_ha_msg  *repmsg;
	uint64_t           tag;

	M0_PRE(hm != NULL);
	M0_PRE(hl != NULL);

	M0_ALLOC_PTR(repmsg);
	M0_ASSERT(repmsg != NULL);
	repmsg->hm_data.hed_type = M0_HA_MSG_FAILURE_VEC_REP;
	// XXX Fabricated pool_fid; fetch the information from Consul.
	repmsg->hm_data.u.hed_fvec_rep.mfp_pool = *pool_fid;
	repmsg->hm_data.u.hed_fvec_rep.mfp_cookie =
		msg->hm_data.u.hed_fvec_req.mfq_cookie;

	repmsg->hm_data.u.hed_fvec_rep.mfp_nr = nr_notes;
	m0_ha_link_send(hl, repmsg, &tag);
	m0_free(repmsg);
}

/* Tests hax - mero nvec reply send. */
static void handle_nvec(const struct hax_msg *hm)
{
	/*
	 * Call python function from here, comment below test function.
	 * XXX TODO: Move out test calls to separate location.
	 */
	nvec_test_reply_send(hm);
}

static void nvec_test_reply_send(const struct hax_msg *hm)
{
	struct m0_ha_msg            *msg = hm->hm_msg;
	const struct m0_ha_msg_nvec *nvec_req = &msg->hm_data.u.hed_nvec;
	struct m0_ha_nvec            nvec = { .nv_nr = nvec_req->hmnv_nr };
	struct m0_fid                obj_fid;
	int                          i;

	M0_LOG(M0_DEBUG, "nvec nv_nr=%"PRIu32" hmvn_type=%s", nvec.nv_nr,
			nvec_req->hmnv_type == M0_HA_NVEC_SET ? "SET" :

	       nvec_req->hmnv_type == M0_HA_NVEC_GET ? "GET" :
			"UNKNOWN!");

	M0_ALLOC_ARR(nvec.nv_note, nvec.nv_nr);
	M0_ASSERT(nvec.nv_note != NULL);

	for (i = 0; i < nvec.nv_nr; ++i) {
		nvec.nv_note[i] = nvec_req->hmnv_arr.hmna_arr[i];
		M0_LOG(M0_DEBUG, "nv_note[%d]=(no_id="FID_F
		       " no_state=%"PRIu32")", i, FID_P(&nvec.nv_note[i].no_id),
		       nvec.nv_note[i].no_state);
	}

	switch (nvec_req->hmnv_type) {
	case M0_HA_NVEC_GET:
		for (i = 0; i < nvec_req->hmnv_nr; ++i) {
			obj_fid = nvec_req->hmnv_arr.hmna_arr[i].no_id;
			/*
			 * XXX Get the state of given object from Consul.
			 * Presently we create a fabricated reply.
			 */
			M0_LOG(M0_DEBUG, "obj == NULL");
			nvec.nv_note[i] = (struct m0_ha_note){
				.no_id = obj_fid,
				.no_state = M0_NC_ONLINE,
			};
		}
		break;
	case M0_HA_NVEC_SET:
		// XXX IMPLEMENTME
		break;
	default:
		M0_IMPOSSIBLE("Unexpected value of hmnv_type: %"PRIu64,
			      nvec_req->hmnv_type);
	}
	__ha_nvec_reply_send(hm, &nvec);
	m0_free(nvec.nv_note);
}

/*
 * Sends nvec reply.
 * To be invoked from python land.
 */
M0_INTERNAL void m0_ha_nvec_reply_send(unsigned long long hm,
				       struct m0_ha_nvec *nvec)
{
	__ha_nvec_reply_send((struct hax_msg *)hm, nvec);
}

static void __ha_nvec_reply_send(const struct hax_msg *hm,
				 struct m0_ha_nvec *nvec)
{
	struct m0_ha_link *hl = hm->hm_hl;
	struct m0_ha_msg  *msg = hm->hm_msg;

	M0_PRE(hm != NULL);
	M0_PRE(nvec != NULL);

	m0_ha_msg_nvec_send(nvec, msg->hm_data.u.hed_nvec.hmnv_id_of_get,
			M0_HA_NVEC_SET, hl);
}

static void handle_process_event(const struct hax_msg *hm)
{
	if (!hm->hm_hc->alive) {
		M0_LOG(M0_DEBUG, "Skipping the event processing since"
		       " Python object is already destructed");
		return;
	}
	PyGILState_STATE gstate;
	gstate = PyGILState_Ensure();

	struct hax_context *hc = hm->hm_hc;
	struct m0_ha_msg   *hmsg = hm->hm_msg;

	PyObject *py_fid = toFid(&hmsg->hm_fid);
	PyObject_CallMethod(hc->hc_handler, "_process_event_cb", "(OKKK)",
			    py_fid,
			    hmsg->hm_data.u.hed_event_process.chp_event,
			    hmsg->hm_data.u.hed_event_process.chp_type,
			    hmsg->hm_data.u.hed_event_process.chp_pid);
	Py_DECREF(py_fid);
	PyGILState_Release(gstate);
}

static void _impossible(const struct hax_msg *hm)
{
	M0_IMPOSSIBLE("Unsupported ha_msg type: %d",
		      m0_ha_msg_type_get(hm->hm_msg);
}

static void (*hax_action[])(const struct hax_msg *hm) = {
	[M0_HA_MSG_STOB_IOQ]        = _impossible,
	[M0_HA_MSG_NVEC]            = handle_nvec,
	[M0_HA_MSG_FAILURE_VEC_REQ] = handle_failvec,
	[M0_HA_MSG_FAILURE_VEC_REP] = handle_failvec,
	[M0_HA_MSG_KEEPALIVE_REQ]   = _impossible,
	[M0_HA_MSG_KEEPALIVE_REP]   = _impossible,
	[M0_HA_MSG_EVENT_PROCESS]   = handle_process_event,
	[M0_HA_MSG_EVENT_SERVICE]   = _impossible,
	[M0_HA_MSG_EVENT_RPC]       = _impossible,
	[M0_HA_MSG_BE_IO_ERR]       = _impossible,
	[M0_HA_MSG_SNS_ERR]         = _impossible,
};

static void msg_received_cb(struct m0_halon_interface *hi,
			    struct m0_ha_link *hl,
			    struct m0_ha_msg *msg,
			    uint64_t tag)
{
	const enum m0_ha_msg_type msg_type = m0_ha_msg_type_get(msg);

	M0_PRE(M0_HA_MSG_INVALID < msg_type && msg_type <= M0_HA_MSG_SNS_ERR);
	M0_LOG(M0_ALWAYS, "Received msg of type %d", m0_ha_msg_type_get(msg));

	hax_action[msg_type](
		&(struct hax_msg){
			.hm_hc = hc,
			.hm_hl = hl,
			.hm_msg = msg
		});
	m0_halon_interface_delivered(hi, hl, msg);
}

static void noop_cb(struct m0_halon_interface *hi,
		    struct m0_ha_link *hl,
		    uint64_t tag)
{
	M0_LOG(M0_NOTICE, "XXX Callback handler is a noop");
}

static void link_is_disconnecting_cb(struct m0_halon_interface *hi,
				     struct m0_ha_link *hl)
{
	M0_LOG(M0_ALWAYS, "Disconnecting ha");
	m0_halon_interface_disconnect(hi, hl);
}

M0_INTERNAL struct hax_context *init_halink(PyObject *obj,
					    const char* node_uuid)
{
	int rc;

	// Since we depend on the Python object, we don't want to let it die
	// before us.
	Py_INCREF(obj);

	hc = malloc(sizeof(*hc));
	assert(hc != NULL);

	hc->alive = true;
	rc = m0_halon_interface_init(&hc->hc_hi, "M0_VERSION_GIT_REV_ID",
			"M0_VERSION_BUILD_CONFIGURE_OPTS",
			"disable-compatibility-check", NULL);
	if (rc != 0) {
		free(hc);
		return 0;
	}
	m0_mutex_init(&hc->hc_mutex);
	M0_SET0(&m0thread);
	m0 = m0_halon_interface_m0_get(hc->hc_hi);

	hc->hc_handler = obj;
	return hc;
}

void destroy_halink(unsigned long long ctx)
{
	struct hax_context *hc = (struct hax_context *)ctx;

	hc->alive = false;
	Py_DECREF(hc->hc_handler);
	m0_mutex_fini(&hc->hc_mutex);
	m0_halon_interface_stop(hc->hc_hi);
	m0_halon_interface_fini(hc->hc_hi);
}

int start(unsigned long long   ctx,
	  const char          *local_rpc_endpoint,
	  const struct m0_fid *process_fid,
	  const struct m0_fid *ha_service_fid,
	  const struct m0_fid *rm_service_fid)
{
	struct hax_context        *hc = (struct hax_context *)ctx;
	struct m0_halon_interface *hi = hc->hc_hi;

	M0_LOG(M0_INFO, "Starting hax interface..\n");
	return m0_halon_interface_start(
		hi, local_rpc_endpoint,
		&M0_FID_TINIT('r', process_fid->f_container,
			      process_fid->f_key),
		&M0_FID_TINIT('s', ha_service_fid->f_container,
			      ha_service_fid->f_key),
		&M0_FID_TINIT('s', rm_service_fid->f_container,
			      rm_service_fid->f_key),
		entrypoint_request_cb,
		msg_received_cb,
		noop_cb, noop_cb, noop_cb, noop_cb,
		link_is_disconnecting_cb,
		noop_cb);
}

void test(unsigned long long ctx)
{
	struct hax_context *hc = (struct hax_context *)ctx;

	M0_LOG(M0_INFO, "Got: %llu\n", ctx);
	M0_LOG(M0_INFO, "Context addr: %p\n", hc);
	M0_LOG(M0_INFO, "handler addr: %p\n", hc->hc_handler);

	struct m0_uint128 t = M0_UINT128(100, 500);
	struct m0_fid fid = M0_FID_INIT(20, 50);

	entrypoint_request_cb( hc->hc_hi, &t, "ENDP", &fid, "GIT", 12345, 0);
}

void m0_ha_broadcast_test(unsigned long long ctx)
{
	struct hax_context *hc = (struct hax_context *)ctx;
	struct m0_ha_note   note;

	note.no_id = M0_FID_TINIT('s', 4, 0);
	note.no_state = M0_NC_ONLINE;

	m0_ha_notify(ctx, &note, 1);
}

void m0_ha_notify(unsigned long long ctx, struct m0_ha_note *notes,
		  uint32_t nr_notes)
{
	struct hax_context        *hc = (struct hax_context *)ctx;
	struct m0_halon_interface *hi = hc->hc_hi;
	struct m0_ha_nvec          nvec = {
		.nv_nr = nr_notes,
		.nv_note = notes
	};
	m0_halon_interface_nvec_broadcast(hi, &nvec);
}

void adopt_mero_thread(void)
{
	int rc = m0_thread_adopt(&m0thread, m0);
	assert(rc == 0);
}

/*
 *  Local variables:
 *  c-indentation-style: "K&R"
 *  c-basic-offset: 8
 *  tab-width: 8
 *  fill-column: 80
 *  scroll-step: 1
 *  End:
 */
