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
#include "conf/obj.h"		/* M0_CONF_OBJ_TYPES */
#include "fid/fid.h"		/* M0_FID_TINIT */
#include "ha/halon/interface.h" /* m0_halon_interface */
#include "spiel/spiel.h"	/* m0_spiel, m0_spiel_filesystem_stats_fetch */
#include "module/instance.h"
#include "lib/assert.h"   /* M0_ASSERT */
#include "lib/memory.h"   /* M0_ALLOC_ARR */
#include "lib/thread.h"   /* m0_thread_{adopt, shun} */
#include "lib/string.h"   /* m0_strdup */
#include "lib/trace.h"    /* M0_LOG, M0_DEBUG */
#include "mero/version.h" /* M0_VERSION_GIT_REV_ID */
#include "mero/iem.h"
#include "ha/msg.h"
#include "ha/link.h"
#include "hax.h"

static struct hax_context *hc0;
static __thread struct m0_thread m0thread;

static void __ha_failvec_reply_send(const struct hax_msg *hm,
				    struct m0_fid *pool_fid, uint32_t nr_notes);
static void nvec_test_reply_send(const struct hax_msg *hm);
static void __ha_nvec_reply_send(const struct hax_msg *hm,
				 struct m0_ha_nvec *nvec);
static struct m0_ha_msg *_ha_nvec_msg_alloc(const struct m0_ha_nvec *nvec,
					    uint64_t id_of_get, int direction);
static PyObject *nvec_to_list(const struct m0_ha_note *notes,
			      uint32_t nr_notes);

M0_TL_DESCR_DEFINE(hx_links, "hax_context::hc_links", static, struct hax_link,
		   hxl_tlink, hxl_magic, 9, 10);
M0_TL_DEFINE(hx_links, static, struct hax_link);

static void hax_lock(struct hax_context *hx)
{
	m0_mutex_lock(&hx->hc_mutex);
}

static void hax_unlock(struct hax_context *hx)
{
	m0_mutex_unlock(&hx->hc_mutex);
}

PyObject *getModule(char *module_name)
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
				  const char *git_rev_id, uint64_t pid,
				  bool first_request)
{
	struct hax_entrypoint_request *ep;

	/*
	 * XXX This is obligatory since we want to work with Python object
	 * and we obviously work from an external thread.
	 * FYI:
	 * https://docs.python.org/2/c-api/init.html#releasing-the-gil-from-extension-code
	 */
	PyGILState_STATE gstate;
	gstate = PyGILState_Ensure();

	M0_ALLOC_PTR(ep);
	M0_ASSERT(ep != NULL);
	ep->hep_hc = hc0;

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
	PyObject_CallMethod(hc0->hc_handler, "_entrypoint_request_cb",
			    "(KOsOsKb)", ep, py_req, remote_rpc_endpoint,
			    py_fid, git_rev_id, pid, first_request);
	Py_DECREF(py_req);
	Py_DECREF(py_fid);
	/* XXX Note that the Python threads get unblocked only after this call.
	 */
	PyGILState_Release(gstate);
}

/*
 * To be invoked from python land.
 */
M0_INTERNAL void m0_ha_entrypoint_reply_send(
    unsigned long long epr, const struct m0_uint128 *req_id, int rc,
    uint32_t confd_nr, const struct m0_fid *confd_fid_data,
    const char **confd_eps_data, uint32_t confd_quorum,
    const struct m0_fid *rm_fid, const char *rm_eps)
{
	struct hax_entrypoint_request *hep =
	    (struct hax_entrypoint_request *)epr;

	m0_halon_interface_entrypoint_reply(
	    hep->hep_hc->hc_hi, req_id, rc, confd_nr, confd_fid_data,
	    confd_eps_data, confd_quorum, rm_fid, rm_eps);
	m0_free(hep);
}

/*
 * To be invoked from python land.
 */
PyObject *m0_ha_filesystem_stats_fetch(unsigned long long ctx)
{
	PyGILState_STATE gstate;
	gstate = PyGILState_Ensure();

	struct hax_context *hc = (struct hax_context *)ctx;
	struct m0_halon_interface *hi = hc->hc_hi;
	struct m0_spiel *spiel = m0_halon_interface_spiel(hi);

	struct m0_fs_stats stats;
	Py_BEGIN_ALLOW_THREADS int rc =
	    m0_spiel_filesystem_stats_fetch(spiel, &stats);
	M0_ASSERT(rc == 0);
	Py_END_ALLOW_THREADS PyObject *hax_mod = getModule("hax.types");
	PyObject *fs_stats = PyObject_CallMethod(
	    hax_mod, "FsStats", "(KKKKKII)", stats.fs_free_seg,
	    stats.fs_total_seg, stats.fs_free_disk, stats.fs_avail_disk,
	    stats.fs_total_disk, stats.fs_svc_total, stats.fs_svc_replied);
	Py_DECREF(hax_mod);
	PyGILState_Release(gstate);
	return fs_stats;
}

static void handle_failvec(const struct hax_msg *hm)
{
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
	M0_PRE(hm != 0);
	__ha_failvec_reply_send((struct hax_msg *)hm, pool_fid, nr_notes);
}

static void __ha_failvec_reply_send(const struct hax_msg *hm,
				    struct m0_fid *pool_fid, uint32_t nr_notes)
{
	struct m0_ha_link *hl = hm->hm_hl;
	struct m0_halon_interface *hif = hm->hm_hc->hc_hi;
	const struct m0_ha_msg *msg = &hm->hm_msg;
	struct m0_ha_msg *repmsg;
	uint64_t tag;

	M0_PRE(hm != NULL);
	M0_PRE(hl != NULL);

	M0_ALLOC_PTR(repmsg);
	M0_ASSERT(repmsg != NULL);
	repmsg->hm_data.hed_type = M0_HA_MSG_FAILURE_VEC_REP;
	repmsg->hm_data.u.hed_fvec_rep.mfp_pool = *pool_fid;
	repmsg->hm_data.u.hed_fvec_rep.mfp_cookie =
	    msg->hm_data.u.hed_fvec_req.mfq_cookie;

	repmsg->hm_data.u.hed_fvec_rep.mfp_nr = nr_notes;
	m0_halon_interface_send(hif, hl, repmsg, &tag);
	m0_free(repmsg);
}

/* Tests hax - mero nvec reply send. */
static void handle_nvec(const struct hax_msg *hm)
{
	struct hax_msg *hmsg;
	const struct m0_ha_msg *msg = &hm->hm_msg;
	const struct m0_ha_msg_nvec *hm_nvec = &msg->hm_data.u.hed_nvec;
	const struct m0_ha_note *ha_notes = hm_nvec->hmnv_arr.hmna_arr;
	uint32_t nr_notes = hm_nvec->hmnv_nr;

	PyGILState_STATE gstate;
	gstate = PyGILState_Ensure();

	M0_ALLOC_PTR(hmsg);
	M0_ASSERT(hmsg != NULL);

	*hmsg = *hm;
	PyObject *l = nvec_to_list(ha_notes, nr_notes);
	PyObject_CallMethod(hc0->hc_handler, "ha_nvec_get", "(KO)", hmsg, l);

	Py_DECREF(l);
	PyGILState_Release(gstate);
}

static const char *conf_obj_type_name(const struct m0_conf_obj_type *obj_t)
{
	switch (obj_t->cot_ftype.ft_id) {
#define X_CONF(_, NAME, FT_ID)                                                 \
	case FT_ID:                                                            \
		return #NAME;

		M0_CONF_OBJ_TYPES
#undef X_CONF
	default:
		;
	}

	M0_IMPOSSIBLE("Invalind ft_id: %c (%u)", obj_t->cot_ftype.ft_id,
		      obj_t->cot_ftype.ft_id);
}

static PyObject *nvec_to_list(const struct m0_ha_note *notes, uint32_t nr_notes)
{
	uint32_t i;
	const struct m0_ha_note *note;
	const char *obj_name;
	PyObject *list = PyList_New(nr_notes);

	PyObject *hax_mod = getModule("hax.types");
	for (i = 0; i < nr_notes; ++i) {
		note = &notes[i];
		PyObject *fid = PyObject_CallMethod(
		    hax_mod, "FidStruct", "(KK)", note->no_id.f_container,
		    note->no_id.f_key);
		PyObject *ha_note = PyObject_CallMethod(
		    hax_mod, "HaNoteStruct", "(OK)", fid, note->no_state);

		obj_name = conf_obj_type_name(m0_conf_fid_type(&note->no_id));
		PyObject *note_item = PyObject_CallMethod(
		    hax_mod, "HaNote", "(sO)", obj_name, ha_note);
		/* Note: this call "steals" reference to note_item which means
		 * that we don't need to call Py_DECREF(note_item)
		 */
		PyList_SET_ITEM(list, i, note_item);
	}
	Py_DECREF(hax_mod);

	return list;
}

static void nvec_test_reply_send(const struct hax_msg *hm)
    __attribute__((unused));
static void nvec_test_reply_send(const struct hax_msg *hm)
{
	const struct m0_ha_msg *msg = &hm->hm_msg;
	const struct m0_ha_msg_nvec *nvec_req = &msg->hm_data.u.hed_nvec;
	struct m0_ha_nvec nvec = { .nv_nr = (int32_t)nvec_req->hmnv_nr };
	struct m0_fid obj_fid;
	int32_t i;

	M0_PRE(M0_IN(nvec_req->hmnv_type, (M0_HA_NVEC_SET, M0_HA_NVEC_GET)));
	M0_LOG(M0_DEBUG, "nvec nv_nr=%" PRIu32 " hmvn_type=M0_HA_NVEC_%s",
	       nvec.nv_nr,
	       nvec_req->hmnv_type == M0_HA_NVEC_SET ? "SET" : "GET");

	M0_ALLOC_ARR(nvec.nv_note, nvec.nv_nr);
	M0_ASSERT(nvec.nv_note != NULL);

	for (i = 0; i < nvec.nv_nr; ++i) {
		nvec.nv_note[i] = nvec_req->hmnv_arr.hmna_arr[i];
		M0_LOG(M0_DEBUG,
		       "nv_note[%d]=(no_id=" FID_F " no_state=%" PRIu32 ")", i,
		       FID_P(&nvec.nv_note[i].no_id), nvec.nv_note[i].no_state);
	}
	switch (nvec_req->hmnv_type) {
	case M0_HA_NVEC_GET:
		for (i = 0; i < (int32_t)nvec_req->hmnv_nr; ++i) {
			obj_fid = nvec_req->hmnv_arr.hmna_arr[i].no_id;
			/*
			 * XXX Get the state of given object from Consul.
			 * Presently we create a fabricated reply.
			 */
			M0_LOG(M0_DEBUG, "obj == NULL");
			nvec.nv_note[i] =
			    (struct m0_ha_note) { .no_id = obj_fid,
						  .no_state = M0_NC_ONLINE, };
		}
		break;
	case M0_HA_NVEC_SET:
		/* XXX IMPLEMENTME */
		break;
	default:
		M0_IMPOSSIBLE("Unexpected value of hmnv_type: %" PRIu64,
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
				       struct m0_ha_note *notes,
				       uint32_t nr_notes)
{
	struct hax_msg *hmsg = (struct hax_msg *)hm;
	struct m0_ha_nvec nvec = { .nv_nr = nr_notes, .nv_note = notes };

	M0_LOG(M0_DEBUG, "nvec->nv_nr=%d hax_msg=%p", nvec.nv_nr, hmsg);
	__ha_nvec_reply_send(hmsg, &nvec);
	m0_free(hmsg);
}

static void __ha_nvec_reply_send(const struct hax_msg *hm,
				 struct m0_ha_nvec *nvec)
{
	M0_PRE(hm != NULL);
	M0_PRE(nvec != NULL);

	struct m0_halon_interface *hi = hm->hm_hc->hc_hi;

	struct m0_ha_link *hl = hm->hm_hl;
	const struct m0_ha_msg *msg = &hm->hm_msg;
	uint64_t tag;

	msg = _ha_nvec_msg_alloc(nvec, msg->hm_data.u.hed_nvec.hmnv_id_of_get,
				 M0_HA_NVEC_SET);
	m0_halon_interface_send(hi, hl, msg, &tag);
}

static void handle_process_event(const struct hax_msg *hm)
{
	if (!hm->hm_hc->hc_alive) {
		M0_LOG(M0_DEBUG, "Skipping the event processing since"
				 " Python object is already destructed");
		return;
	}
	PyGILState_STATE gstate;
	gstate = PyGILState_Ensure();

	struct hax_context *hc = hm->hm_hc;
	const struct m0_ha_msg *hmsg = &hm->hm_msg;

	M0_LOG(M0_INFO, "Process fid: " FID_F, FID_P(&hmsg->hm_fid));
	PyObject *py_fid = toFid(&hmsg->hm_fid);
	PyObject_CallMethod(hc->hc_handler, "_process_event_cb", "(OKKK)",
			    py_fid, hmsg->hm_data.u.hed_event_process.chp_event,
			    hmsg->hm_data.u.hed_event_process.chp_type,
			    hmsg->hm_data.u.hed_event_process.chp_pid);
	Py_DECREF(py_fid);
	PyGILState_Release(gstate);
}

static void handle_stob_ioq(const struct hax_msg *hm)
{
	const struct m0_stob_ioq_error *ioq_err =
	    &hm->hm_msg.hm_data.u.hed_stob_ioq;
	char buf[512] = { 0 };

	/*
	 * This IEM was disabled temporarily.
	 *
	 * There is no justification for this arbitrary decision. This was
	 * wrong thing to do in the first place, but we were forced to do it
	 * after ~15h of meetings.
	 * Now we need to disable this, and it took only several hours of
	 * discussions in private chats and 1h meeting with several managements
	 * and architects present.
	 */
	return;

	snprintf(buf, sizeof(buf) - 1,
		 "%x|" FID_F "|" FID_F "|" FID_F "|%" PRIx64 "|%" PRIx64
		 "|%" PRIx64 "|%" PRIx64 "|%" PRIx64 "|%" PRIx32,
		 m0_ha_msg_type_get(&hm->hm_msg),
		 FID_P(&ioq_err->sie_conf_sdev),
		 FID_P(&ioq_err->sie_stob_id.si_domain_fid),
		 FID_P(&ioq_err->sie_stob_id.si_fid), ioq_err->sie_fd,
		 ioq_err->sie_opcode, ioq_err->sie_rc, ioq_err->sie_offset,
		 ioq_err->sie_size, ioq_err->sie_bshift);

	M0_MERO_IEM_DESC(M0_MERO_IEM_SEVERITY_A_ALERT, M0_MERO_IEM_MODULE_IO,
			 M0_MERO_IEM_EVENT_IOQ, "stob_ioq_error [%s]", buf);
}

static void _dummy_handle(const struct hax_msg *msg)
{
	/*
	 * This function handles few events that are received but
	 * can be ignored. Relevant implementation can be added as
	 * required.
	 */
}

static void _impossible(const struct hax_msg *hm)
{
	M0_IMPOSSIBLE("Unsupported ha_msg type: %d",
		      m0_ha_msg_type_get(&hm->hm_msg));
}

static void (*hax_action[])(const struct hax_msg *hm) =
    {[M0_HA_MSG_STOB_IOQ] = handle_stob_ioq,
     [M0_HA_MSG_NVEC] = handle_nvec,
     [M0_HA_MSG_FAILURE_VEC_REQ] = handle_failvec,
     [M0_HA_MSG_FAILURE_VEC_REP] = handle_failvec,
     [M0_HA_MSG_KEEPALIVE_REQ] = _impossible,
     [M0_HA_MSG_KEEPALIVE_REP] = _impossible,
     [M0_HA_MSG_EVENT_PROCESS] = handle_process_event,
     [M0_HA_MSG_EVENT_SERVICE] = _dummy_handle,
     [M0_HA_MSG_EVENT_RPC] = _dummy_handle,
     [M0_HA_MSG_BE_IO_ERR] = _impossible,
     [M0_HA_MSG_SNS_ERR] = _impossible, };

static void msg_received_cb(struct m0_halon_interface *hi,
			    struct m0_ha_link *hl, const struct m0_ha_msg *msg,
			    uint64_t tag)
{
	const enum m0_ha_msg_type msg_type = m0_ha_msg_type_get(msg);

	M0_PRE(M0_HA_MSG_INVALID < msg_type && msg_type <= M0_HA_MSG_SNS_ERR);
	M0_LOG(M0_INFO, "Received msg of type %d", m0_ha_msg_type_get(msg));

	hax_action[msg_type](
	    &(struct hax_msg) { .hm_hc = hc0, .hm_hl = hl, .hm_msg = *msg });
	m0_halon_interface_delivered(hi, hl, msg);
}

static void msg_is_delivered_cb(struct m0_halon_interface *hi,
				struct m0_ha_link *hl, uint64_t tag)
{
	M0_LOG(M0_DEBUG, "noop");
}

static void msg_is_not_delivered_cb(struct m0_halon_interface *hi,
				    struct m0_ha_link *hl, uint64_t tag)
{
	M0_LOG(M0_DEBUG, "noop");
}

static void link_connected_cb(struct m0_halon_interface *hi,
			      const struct m0_uint128 *req_id,
			      struct m0_ha_link *link)
{
	struct hax_link *hxl;

	M0_ALLOC_PTR(hxl);
	if (hxl == NULL) {
		M0_LOG(M0_ERROR, "Cannot allocate hax_link");
		return;
	}
	hxl->hxl_link = link;
	hax_lock(hc0);
	hx_links_tlink_init_at_tail(hxl, &hc0->hc_links);
	hax_unlock(hc0);
}

static void link_reused_cb(struct m0_halon_interface *hi,
			   const struct m0_uint128 *req_id,
			   struct m0_ha_link *link)
{
	M0_LOG(M0_DEBUG, "noop");
}

static void link_absent_cb(struct m0_halon_interface *hi,
			   const struct m0_uint128 *req_id)
{
	M0_LOG(M0_DEBUG, "noop");
}

static void link_is_disconnecting_cb(struct m0_halon_interface *hi,
				     struct m0_ha_link *hl)
{
	m0_halon_interface_disconnect(hi, hl);
}

static void link_disconnected_cb(struct m0_halon_interface *hi,
				 struct m0_ha_link *link)
{
	struct hax_link *hxl_out;

	hax_lock(hc0);
	hxl_out = m0_tl_find(
	    hx_links, hxl, &hc0->hc_links,
	    m0_uint128_eq(&hxl->hxl_link->hln_conn_cfg.hlcc_params.hlp_id_local,
			  &link->hln_conn_cfg.hlcc_params.hlp_id_local) &&
		m0_uint128_eq(
		    &hxl->hxl_link->hln_conn_cfg.hlcc_params.hlp_id_remote,
		    &link->hln_conn_cfg.hlcc_params.hlp_id_remote));
	if (hxl_out != NULL) {
		hx_links_tlink_del_fini(hxl_out);
		m0_free(hxl_out);
	}
	hax_unlock(hc0);
}

M0_INTERNAL struct hax_context *init_halink(PyObject *obj,
					    const char *node_uuid)
{
	int rc;

	/* Since we depend on the Python object, we don't want to let
	 * it die before us.
	 */
	Py_INCREF(obj);

	hc0 = malloc(sizeof(*hc0));
	assert(hc0 != NULL);

	hc0->hc_alive = true;
	hx_links_tlist_init(&hc0->hc_links);
	m0_mutex_init(&hc0->hc_mutex);
	rc = m0_halon_interface_init(&hc0->hc_hi, M0_VERSION_GIT_REV_ID,
				     M0_VERSION_BUILD_CONFIGURE_OPTS,
				     "log-entrypoint log-link log-msg", NULL);
	if (rc != 0) {
		hx_links_tlist_fini(&hc0->hc_links);
		m0_mutex_fini(&hc0->hc_mutex);
		free(hc0);
		return NULL;
	}
	hc0->hc_handler = obj;
	return hc0;
}

void destroy_halink(unsigned long long ctx)
{
	struct hax_context *hc = (struct hax_context *)ctx;

	hc->hc_alive = false;
	Py_DECREF(hc->hc_handler);
	if (hc->hc_rconfc_initialized) {
		struct m0_spiel *spiel = m0_halon_interface_spiel(hc0->hc_hi);
		m0_spiel_rconfc_stop(spiel);
	}

	m0_halon_interface_stop(hc->hc_hi);
	m0_halon_interface_fini(hc->hc_hi);
	m0_mutex_fini(&hc->hc_mutex);
	hx_links_tlist_fini(&hc->hc_links);
}

int start(unsigned long long ctx, const char *local_rpc_endpoint,
	  const struct m0_fid *process_fid, const struct m0_fid *ha_service_fid,
	  const struct m0_fid *rm_service_fid)
{
	struct hax_context *hc = (struct hax_context *)ctx;
	struct m0_halon_interface *hi = hc->hc_hi;

	M0_LOG(M0_INFO, "Starting hax interface..\n");
	int rc = m0_halon_interface_start(
	    hi, local_rpc_endpoint,
	    &M0_FID_TINIT('r', process_fid->f_container, process_fid->f_key),
	    &M0_FID_TINIT('s', ha_service_fid->f_container,
			  ha_service_fid->f_key),
	    &M0_FID_TINIT('s', rm_service_fid->f_container,
			  rm_service_fid->f_key),
	    entrypoint_request_cb, msg_received_cb, msg_is_delivered_cb,
	    msg_is_not_delivered_cb, link_connected_cb, link_reused_cb,
	    link_absent_cb, link_is_disconnecting_cb, link_disconnected_cb);
	if (rc != 0) {
		M0_LOG(M0_ERROR, "Failed to start m0_halon_interface");
	}
	return rc;
}

int start_rconfc(unsigned long long ctx, const struct m0_fid *process_fid)
{
	struct hax_context *hc = (struct hax_context *)ctx;

	struct m0_spiel *spiel = m0_halon_interface_spiel(hc->hc_hi);
	char fid_str[M0_FID_STR_LEN];

	struct m0_fid *process_fid_copy =
	    &M0_FID_TINIT('r', process_fid->f_container, process_fid->f_key);

	m0_fid_print(fid_str, M0_FID_STR_LEN, process_fid_copy);
	int rc = m0_spiel_cmd_profile_set(spiel, fid_str);
	if (rc != 0) {
		M0_LOG(M0_ERROR, "Failed to set spiel profile");
		return rc;
	}
	rc = m0_spiel_rconfc_start(spiel, NULL);
	if (rc != 0) {
		M0_LOG(M0_ERROR, "Failed to start rconfc");
		return rc;
	}
	hc->hc_rconfc_initialized = true;
	return 0;
}

void test(unsigned long long ctx)
{
	struct hax_context *hc = (struct hax_context *)ctx;

	M0_LOG(M0_INFO, "Got: %llu\n", ctx);
	M0_LOG(M0_INFO, "Context addr: %p\n", hc);
	M0_LOG(M0_INFO, "handler addr: %p\n", hc->hc_handler);

	struct m0_uint128 t = M0_UINT128(100, 500);
	struct m0_fid fid = M0_FID_INIT(20, 50);

	entrypoint_request_cb(hc->hc_hi, &t, "ENDP", &fid, "GIT", 12345, 0);
}

void m0_ha_broadcast_test(unsigned long long ctx)
{
	struct m0_ha_note note = { .no_id = M0_FID_TINIT('s', 4, 0),
				   .no_state = M0_NC_ONLINE };
	m0_ha_notify(ctx, &note, 1);
}

void m0_ha_notify(unsigned long long ctx, struct m0_ha_note *notes,
		  uint32_t nr_notes)
{
	struct hax_context *hc = (struct hax_context *)ctx;
	struct m0_ha_nvec nvec = { .nv_nr = nr_notes, .nv_note = notes };
	struct m0_halon_interface *hi = hc->hc_hi;
	struct hax_link *hxl;
	struct m0_ha_msg *msg;
	uint64_t tag;

	msg = _ha_nvec_msg_alloc(&nvec, 0, M0_HA_NVEC_SET);
	hax_lock(hc0);
	m0_tl_for(hx_links, &hc->hc_links, hxl)
	{
		m0_halon_interface_send(hi, hxl->hxl_link, msg, &tag);
	}
	m0_tl_endfor;
	hax_unlock(hc0);
}

static struct m0_ha_msg *_ha_nvec_msg_alloc(const struct m0_ha_nvec *nvec,
					    uint64_t id_of_get, int direction)
{
	struct m0_ha_msg *msg;

	M0_ALLOC_PTR(msg);
	M0_ASSERT(msg != NULL);
	*msg = (struct m0_ha_msg) {
		.hm_data = { .hed_type = M0_HA_MSG_NVEC,
			     .u.hed_nvec = { .hmnv_type = direction,
					     .hmnv_id_of_get = id_of_get,
					     .hmnv_ignore_same_state = 1,
					     .hmnv_nr = nvec->nv_nr, }, },
	};
	M0_ASSERT(
	    nvec->nv_nr > 0 &&
	    nvec->nv_nr <=
		(int)ARRAY_SIZE(msg->hm_data.u.hed_nvec.hmnv_arr.hmna_arr));
	memcpy(msg->hm_data.u.hed_nvec.hmnv_arr.hmna_arr, nvec->nv_note,
	       nvec->nv_nr * sizeof(nvec->nv_note[0]));
	return msg;
}

void adopt_mero_thread(void)
{
	int rc;

	rc = m0_halon_interface_thread_adopt(hc0->hc_hi, &m0thread);
	if (rc != 0)
		M0_LOG(M0_ERROR, "Mero thread adoption failed: %d\n", rc);
}

void shun_mero_thread(void)
{
	m0_halon_interface_thread_shun();
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
