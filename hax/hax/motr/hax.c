/*
 * Copyright (c) 2020 Seagate Technology LLC and/or its Affiliates
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 * For any questions about this software or licensing,
 * please email opensource@seagate.com or cortx-questions@seagate.com.
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
#include "conf/pvers.h"		 /* m0_conf_pver_info, m0_conf_pver_state */
#include "module/instance.h"
#include "lib/assert.h"   /* M0_ASSERT */
#include "lib/memory.h"   /* M0_ALLOC_ARR */
#include "lib/thread.h"   /* m0_thread_{adopt, shun} */
#include "lib/string.h"   /* m0_strdup */
#include "motr/version.h" /* M0_VERSION_GIT_REV_ID */
#include "motr/iem.h"
#include "ha/msg.h"
#include "ha/link.h"
#include "ha/ha.h"
#include "cm/repreb/cm.h" /* CM_OP_REPAIR etc. */
#include "conf/ha.h"
#include "hax.h"
#include "addb2/global.h"
#include "conf/rconfc.h"

#define M0_TRACE_SUBSYSTEM M0_TRACE_SUBSYS_HA
#include "lib/trace.h"    /* M0_LOG, M0_DEBUG */

static struct hax_context *hc0;

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
	struct hax_context *hc = (struct hax_context *)ctx;
	struct m0_halon_interface *hi = hc->hc_hi;
	struct m0_spiel *spiel = m0_halon_interface_spiel(hi);

	struct m0_fs_stats stats;
	int rc;

	PyGILState_STATE gstate;
	gstate = PyGILState_Ensure();
	Py_BEGIN_ALLOW_THREADS rc =
	    m0_spiel_filesystem_stats_fetch(spiel, &stats);
	Py_END_ALLOW_THREADS if (rc != 0)
	{
		PyGILState_Release(gstate);
		// This returns None python object (which is a singleton)
		// properly with respect to reference counters.
		Py_RETURN_NONE;
	}
	PyObject *hax_mod = getModule("hax.types");
	PyObject *fs_stats = PyObject_CallMethod(
	    hax_mod, "FsStats", "(KKKKKII)", stats.fs_free_seg,
	    stats.fs_total_seg, stats.fs_free_disk, stats.fs_avail_disk,
	    stats.fs_total_disk, stats.fs_svc_total, stats.fs_svc_replied);
	Py_DECREF(hax_mod);
	PyGILState_Release(gstate);
	return fs_stats;
}

/*
 * To be invoked from python land.
 */
PyObject *m0_ha_proc_counters_fetch(unsigned long long ctx,
	struct m0_fid *proc_fid)
{
	struct hax_context *hc = (struct hax_context *)ctx;
	struct m0_halon_interface *hi = hc->hc_hi;
	struct m0_spiel *spiel = m0_halon_interface_spiel(hi);

	struct m0_proc_counter *count_stats=NULL;
	int rc;

	PyGILState_STATE gstate;
	gstate = PyGILState_Ensure();
	/* init count_stats */
	Py_BEGIN_ALLOW_THREADS rc = 
	    m0_spiel_count_stats_init(&count_stats);
	Py_END_ALLOW_THREADS if (rc != 0)
        {
                PyGILState_Release(gstate);
                Py_RETURN_NONE;
        }

	/* call the motr api */
	Py_BEGIN_ALLOW_THREADS rc =
	    m0_spiel_proc_counters_fetch(spiel, proc_fid, count_stats);
	Py_END_ALLOW_THREADS if (rc != 0)
	{
		PyGILState_Release(gstate);
		/* This returns None python object (which is a singleton)
		   properly with respect to reference counters. */
		Py_RETURN_NONE;
	}

	PyObject *hax_mod = getModule("hax.types");
	PyObject *py_fid = toFid(&count_stats->pc_proc_fid);
	int len = count_stats->pc_cnt;
	/* Fetch all byte count stats per pver. */
	PyObject *list = PyList_New(len);
	int i;
	for (i = 0; i < len; ++i) {
		PyObject *pver_fid = toFid(&count_stats->pc_bckey[i]->sbk_fid);
		PyObject *pver_bc = PyObject_CallMethod(
			hax_mod, "PverBC", "(OKKI)",
			pver_fid,
			count_stats->pc_bckey[i]->sbk_user_id,
			count_stats->pc_bcrec[i]->sbr_byte_count,
			count_stats->pc_bcrec[i]->sbr_object_count
		);
		PyList_SET_ITEM(list, i, pver_bc);
	}

	/* Free proc_count_stats */
	m0_spiel_count_stats_fini(count_stats);

	PyObject *bc_stats = PyObject_CallMethod(
	    hax_mod, "ByteCountStats", "(OO)",
		py_fid,
		list);
	Py_DECREF(list);
	Py_DECREF(hax_mod);
	PyGILState_Release(gstate);
	return bc_stats;
}

/*
 * To be invoked from python land.
 */
PyObject *m0_ha_pver_status(unsigned long long ctx,
	struct m0_fid *pver_fid)
{
	struct hax_context *hc = (struct hax_context *)ctx;
	struct m0_halon_interface *hi = hc->hc_hi;
	struct m0_spiel *spiel = m0_halon_interface_spiel(hi);

	struct m0_conf_pver_info pver_info;

	int rc;

	PyGILState_STATE gstate;
	gstate = PyGILState_Ensure();
	/* call the motr api */
	Py_BEGIN_ALLOW_THREADS rc =
	    m0_spiel_conf_pver_status(spiel, pver_fid, &pver_info);
	Py_END_ALLOW_THREADS if (rc != 0)
	{
		PyGILState_Release(gstate);
		/* This returns None python object (which is a singleton)
		   properly with respect to reference counters. */
		Py_RETURN_NONE;
	}
	M0_LOG(M0_INFO, "FID:"FID_F", Status:%d, attributes:N=%d"
			" K=%d, P=%d",
		FID_P(&pver_info.cpi_fid), pver_info.cpi_state,
		pver_info.cpi_attr.pa_N, pver_info.cpi_attr.pa_K,
		pver_info.cpi_attr.pa_P);

	PyObject *hax_mod = getModule("hax.types");
	PyObject *pfid = toFid(&pver_info.cpi_fid);
	PyObject *pinfo = PyObject_CallMethod(
			hax_mod, "PverInfo", "(OIIIII)",
			pfid, pver_info.cpi_state,
			pver_info.cpi_attr.pa_N, pver_info.cpi_attr.pa_K,
			pver_info.cpi_attr.pa_P, pver_info.cpi_attr.pa_unit_size);

	PyGILState_Release(gstate);
	return pinfo;
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
	struct m0_ha_link *hl = NULL;
	struct m0_halon_interface *hif = NULL;
	const struct m0_ha_msg *msg;
	struct m0_ha_msg *repmsg;
	uint64_t tag;

	M0_PRE(hm != NULL);

	hl = hm->hm_hl;
	M0_PRE(hl != NULL);

	M0_PRE(hm->hm_hc != NULL);
	hif = hm->hm_hc->hc_hi;

	msg = &hm->hm_msg;

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

/* Tests hax - motr nvec reply send. */
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
	if (hm_nvec->hmnv_type == M0_HA_NVEC_GET)
		PyObject_CallMethod(hc0->hc_handler, "ha_nvec_get", "(KO)", hmsg, l);
	else if (hm_nvec->hmnv_type == M0_HA_NVEC_SET)
		PyObject_CallMethod(hc0->hc_handler, "ha_nvec_set", "(KO)", hmsg, l);
	else
		M0_IMPOSSIBLE("invalid M0_HA_NVEC_type");

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
	PyObject *list = PyList_New(nr_notes);

	PyObject *hax_mod = getModule("hax.types");
	for (i = 0; i < nr_notes; ++i) {
		const char *obj_name;
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
		M0_LOG(M0_WARN, "Skipping the event processing since"
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
	M0_ENTRY();
	M0_LOG(M0_WARN, "Got STOB_IOQ");

	if (!hm->hm_hc->hc_alive) {
		M0_LOG(M0_WARN, "Skipping the event processing since"
				 " Python object is already destructed");
		M0_LEAVE();
		return;
	}

	PyGILState_STATE gstate;
	gstate = PyGILState_Ensure();

	struct hax_context *hc = hm->hm_hc;
	const struct m0_ha_msg *hmsg = &hm->hm_msg;

	M0_LOG(M0_INFO, "Stob fid: " FID_F, FID_P(&hmsg->hm_fid));

	PyObject *py_fid = toFid(&hmsg->hm_fid);
	PyObject *py_conf_sdev = toFid(&hmsg->hm_data.u.hed_stob_ioq.sie_conf_sdev);
	PyObject *py_stob_id_dom_fid = toFid(&hmsg->hm_data.u.hed_stob_ioq.sie_stob_id.si_domain_fid);
	PyObject *py_stob_id_fid = toFid(&hmsg->hm_data.u.hed_stob_ioq.sie_stob_id.si_fid);
	PyObject *hax_mod = getModule("hax.types");
	PyObject *py_stob_id = PyObject_CallMethod(hax_mod, "StobId", "(OO)",
					py_stob_id_dom_fid, py_stob_id_fid);

	PyObject_CallMethod(hc->hc_handler, "_stob_ioq_event_cb", "(OOOKKKKKI)",
			    py_fid, py_conf_sdev, py_stob_id,
			    hmsg->hm_data.u.hed_stob_ioq.sie_fd,
			    hmsg->hm_data.u.hed_stob_ioq.sie_opcode,
			    hmsg->hm_data.u.hed_stob_ioq.sie_rc,
			    hmsg->hm_data.u.hed_stob_ioq.sie_offset,
			    hmsg->hm_data.u.hed_stob_ioq.sie_size,
			    hmsg->hm_data.u.hed_stob_ioq.sie_bshift);

	Py_DECREF(py_stob_id);
	Py_DECREF(hax_mod);
	Py_DECREF(py_stob_id_fid);
	Py_DECREF(py_stob_id_dom_fid);
	Py_DECREF(py_conf_sdev);
	Py_DECREF(py_fid);
	PyGILState_Release(gstate);

	M0_LEAVE();
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
	M0_IMPOSSIBLE("Unexpected ha_msg type: %d",
		      m0_ha_msg_type_get(&hm->hm_msg));
}

static void _warn_handle(const struct hax_msg *hm)
{
	M0_LOG(M0_WARN, "Unsupported ha_msg type: %d, ignoring",
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
     [M0_HA_MSG_SNS_ERR] = _warn_handle, };

static void msg_received_cb(struct m0_halon_interface *hi,
			    struct m0_ha_link *hl, const struct m0_ha_msg *msg,
			    uint64_t tag)
{
	const enum m0_ha_msg_type msg_type = m0_ha_msg_type_get(msg);

	M0_PRE(M0_HA_MSG_INVALID < msg_type && msg_type <= M0_HA_MSG_SNS_ERR);
	M0_LOG(M0_INFO, "Received msg of type %d\n", m0_ha_msg_type_get(msg));

	hax_action[msg_type](
	    &(struct hax_msg) { .hm_hc = hc0, .hm_hl = hl, .hm_msg = *msg });
	m0_halon_interface_delivered(hi, hl, msg);
}

static void msg_is_delivered_cb(struct m0_halon_interface *hi,
				struct m0_ha_link *hl, uint64_t tag)
{
	struct m0_fid *proc_fid = &hl->hln_conn_cfg.hlcc_rpc_service_fid;

	PyGILState_STATE gstate;
	gstate = PyGILState_Ensure();

	M0_LOG(M0_DEBUG, "msg delivered, tag=%"PRIu64,
		hl->hln_tag_broadcast_delivery);

	PyObject *py_fid = toFid(proc_fid);
	PyObject_CallMethod(hc0->hc_handler, "_msg_delivered_cb", "(OsKK)",
			    py_fid, hl->hln_conn_cfg.hlcc_rpc_endpoint,
			    tag, hl);
	Py_DECREF(py_fid);
	PyGILState_Release(gstate);
}

static void msg_is_not_delivered_cb(struct m0_halon_interface *hi,
				    struct m0_ha_link *hl, uint64_t tag)
{
	struct m0_fid *proc_fid = &hl->hln_conn_cfg.hlcc_rpc_service_fid;

	PyGILState_STATE gstate;
	gstate = PyGILState_Ensure();

	/* Notify hax about delivery failure. */
	M0_LOG(M0_DEBUG, "msg not delivered, tag=%"PRIu64,
		hl->hln_tag_broadcast_delivery);

	PyObject *py_fid = toFid(proc_fid);
	PyObject_CallMethod(hc0->hc_handler, "_msg_not_delivered_cb", "(OsKK)",
			    py_fid, hl->hln_conn_cfg.hlcc_rpc_endpoint,
			    tag, hl);
	Py_DECREF(py_fid);
	PyGILState_Release(gstate);
}

static void link_connected_cb(struct m0_halon_interface *hi,
			      const struct m0_uint128 *req_id,
			      struct m0_ha_link *link)
{

	struct hax_link *hxl;

	hax_lock(hc0);
	M0_ALLOC_PTR(hxl);
	M0_ASSERT(hxl != NULL);
	m0_ha_link_rpc_endpoint(link, hxl->hxl_ep_addr, EP_ADDR_BUF_SIZE);
	hxl->hxl_req_id = *req_id;
	hxl->hxl_link = link;
	hxl->hxl_is_active = true;
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
				     struct m0_ha_link *link)
{
	struct hax_link *hxl;

	hax_lock(hc0);
	hxl = m0_tl_find(hx_links, l, &hc0->hc_links, l->hxl_link == link);
	M0_ASSERT(hxl != NULL);
	M0_LOG(M0_DEBUG, "link=%p addr=%s", hxl, (const char*)hxl->hxl_ep_addr);
	hxl->hxl_is_active = false;
	m0_halon_interface_disconnect(hi, link);
	hax_unlock(hc0);
}

static void link_disconnected_cb(struct m0_halon_interface *hi,
				 struct m0_ha_link *link)
{
	struct hax_link *hxl;

	hax_lock(hc0);
	hxl = m0_tl_find(hx_links, l, &hc0->hc_links, l->hxl_link == link);
	if (hxl != NULL) {
		M0_LOG(M0_DEBUG, "link=%p addr=%s", hxl,
		       (const char*)hxl->hxl_ep_addr);
		hx_links_tlink_del_fini(hxl);
		m0_free(hxl);
	}
	hax_unlock(hc0);
}

M0_INTERNAL struct hax_context *init_motr_api(PyObject *obj,
					      const char *node_uuid)
{
        struct hax_context *hc;
	int rc;

	/* Since we depend on the Python object, we don't want to let
	 * it die before us.
	 */
	Py_INCREF(obj);

	hc = malloc(sizeof(struct hax_context));
	assert(hc != NULL);

	hc->hc_alive = true;
	hx_links_tlist_init(&hc->hc_links);
	m0_mutex_init(&hc->hc_mutex);
	rc = m0_halon_interface_init(&hc->hc_hi, M0_VERSION_GIT_REV_ID,
				     M0_VERSION_BUILD_CONFIGURE_OPTS,
				     "disable-compatibility-check log-entrypoint log-link log-msg", NULL);
	if (rc != 0) {
		hx_links_tlist_fini(&hc->hc_links);
		m0_mutex_fini(&hc->hc_mutex);
		free(hc);
		return NULL;
	}
	hc->hc_handler = obj;
        hc0 = hc;

	return hc;
}

void motr_api_stop(unsigned long long ctx)
{
	struct hax_context *hc = (struct hax_context *)ctx;

	hc->hc_alive = false;
	m0_halon_interface_stop(hc->hc_hi);
}

void motr_api_fini(unsigned long long ctx)
{
	struct hax_context *hc = (struct hax_context *)ctx;

	m0_addb2_global_thread_leave();
	m0_halon_interface_fini(hc->hc_hi);
	m0_mutex_fini(&hc->hc_mutex);
	hx_links_tlist_fini(&hc->hc_links);
	free(hc);
}

int start(unsigned long long ctx, const char *local_rpc_endpoint,
	  const struct m0_fid *process_fid, const struct m0_fid *ha_service_fid,
	  const struct m0_fid *rm_service_fid)
{
	struct hax_context *hc = (struct hax_context *)ctx;
	struct m0_halon_interface *hi = hc->hc_hi;
	int rc;

	rc = m0_trace_set_immediate_mask("ha");
	if (rc != 0) {
		M0_LOG(M0_ERROR, "Failed to set m0_trace_immediate_mask");
		return rc;
	}

	rc = m0_trace_set_level("info+");
	if (rc != 0) {
		M0_LOG(M0_ERROR, "Failed to set m0_trace_level");
		return rc;
	}

	M0_LOG(M0_INFO, "Starting hax interface..\n");
	rc = m0_halon_interface_start(
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

int start_rconfc(unsigned long long ctx, const struct m0_fid *profile_fid)
{
	struct hax_context *hc = (struct hax_context *)ctx;

	struct m0_spiel *spiel = m0_halon_interface_spiel(hc->hc_hi);
	char fid_str[M0_FID_STR_LEN];

	struct m0_fid *profile_fid_copy =
	    &M0_FID_TINIT('r', profile_fid->f_container, profile_fid->f_key);

	m0_fid_print(fid_str, M0_FID_STR_LEN, profile_fid_copy);
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


int stop_rconfc(unsigned long long ctx)
{
        struct hax_context *hc = (struct hax_context *)ctx;

	if (hc->hc_rconfc_initialized) {
		struct m0_spiel *spiel = m0_halon_interface_spiel(hc->hc_hi);
		m0_spiel_rconfc_stop(spiel);
	}

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
	m0_ha_notify(ctx, &note, 1, NULL, 0);
}

PyObject* m0_ha_notify(unsigned long long ctx, struct m0_ha_note *notes,
		       uint32_t nr_notes, const char **proc_skip_list,
		       uint32_t proc_skip_list_len)
{
	struct hax_context *hc = (struct hax_context *)ctx;
	struct m0_ha_nvec nvec = { .nv_nr = nr_notes, .nv_note = notes };
	struct m0_halon_interface *hi = hc->hc_hi;
	struct hax_link *hxl;
	struct m0_ha_msg *msg;
	uint64_t tag;
        uint32_t i;
        bool skip_process = false;

	msg = _ha_nvec_msg_alloc(&nvec, 0, M0_HA_NVEC_SET);

	hax_lock(hc);
	PyGILState_STATE gstate;
	gstate = PyGILState_Ensure();

	PyObject* hax_mod = getModule("hax.types");
	PyObject* broadcast_tags = PyList_New(0);

	m0_tl_for(hx_links, &hc->hc_links, hxl)
	{
		if (!hxl->hxl_is_active)
			continue;
		skip_process = false;
                for (i = 0; i < proc_skip_list_len; ++i) {
			if (m0_streq(hxl->hxl_ep_addr, proc_skip_list[i])) {
				skip_process = true;
				break;
			}
		}
		if (skip_process)
			continue;
		Py_BEGIN_ALLOW_THREADS
		m0_halon_interface_send(hi, hxl->hxl_link, msg, &tag);
		Py_END_ALLOW_THREADS
		PyObject *instance = PyObject_CallMethod(hax_mod,
							 "MessageId", "(KK)",
							 hxl->hxl_link, tag);
		PyList_Append(broadcast_tags, instance);
	}
	m0_tl_endfor;
	Py_DECREF(hax_mod);
	PyGILState_Release(gstate);
	hax_unlock(hc);

	return broadcast_tags;
}

PyObject* m0_ha_notify_hax_only(unsigned long long ctx,
				struct m0_ha_note *notes,
				uint32_t nr_notes,
				const char *hax_endpoint)
{
	struct hax_context *hc = (struct hax_context *)ctx;
	struct m0_ha_nvec nvec = { .nv_nr = nr_notes, .nv_note = notes };
	struct m0_halon_interface *hi = hc->hc_hi;
	struct hax_link *hxl;
	struct m0_ha_msg *msg;
	uint64_t tag;

	msg = _ha_nvec_msg_alloc(&nvec, 0, M0_HA_NVEC_SET);

	hax_lock(hc);
	PyGILState_STATE gstate;
	gstate = PyGILState_Ensure();

	PyObject* hax_mod = getModule("hax.types");
	PyObject* broadcast_tags = PyList_New(0);
	m0_tl_for(hx_links, &hc->hc_links, hxl)
	{
		if (!hxl->hxl_is_active)
			continue;
		if (m0_streq(hxl->hxl_ep_addr, hax_endpoint)) {
			Py_BEGIN_ALLOW_THREADS
			m0_halon_interface_send(hi, hxl->hxl_link,
						msg, &tag);
			Py_END_ALLOW_THREADS
			PyObject *instance = PyObject_CallMethod(hax_mod,
							"MessageId", "(KK)",
							hxl->hxl_link, tag);
			PyList_Append(broadcast_tags, instance);
		}
	}
	m0_tl_endfor;
	Py_DECREF(hax_mod);
	PyGILState_Release(gstate);
	hax_unlock(hc);

	return broadcast_tags;
}

PyObject* m0_hax_stop(unsigned long long ctx, const struct m0_fid *process_fid,
		      const char *hax_endpoint)
{
	struct m0_ha_msg   *msg;
	struct hax_context *hc = (struct hax_context *)ctx;
	struct m0_halon_interface *hi = hc->hc_hi;
	struct hax_link *hxl;
	uint64_t tag;

	M0_ALLOC_PTR(msg);
	M0_ASSERT(msg != NULL);
        *msg = (struct m0_ha_msg){
                .hm_fid  = *process_fid,
                .hm_time = m0_time_now(),
                .hm_data = {
                        .hed_type            = M0_HA_MSG_EVENT_PROCESS,
                        .u.hed_event_process = {
                                .chp_event = M0_CONF_HA_PROCESS_STOPPED,
                                .chp_type  = M0_CONF_HA_PROCESS_OTHER,
                                .chp_pid   = 0,
                        },
                },
        };

	hax_lock(hc);
	PyGILState_STATE gstate;
	gstate = PyGILState_Ensure();
	PyObject* hax_mod = getModule("hax.types");
	PyObject* broadcast_tags = PyList_New(0);
	m0_tl_for(hx_links, &hc->hc_links, hxl) {
		if (!hxl->hxl_is_active)
			continue;
		if (m0_streq(hxl->hxl_ep_addr, hax_endpoint)) {
			Py_BEGIN_ALLOW_THREADS
			m0_halon_interface_send(hi, hxl->hxl_link, msg, &tag);
			Py_END_ALLOW_THREADS
			PyObject *instance = PyObject_CallMethod(hax_mod,
							"MessageId", "(KK)",
							hxl->hxl_link, tag);
			PyList_Append(broadcast_tags, instance);
		}
	} m0_tl_endfor;
	Py_DECREF(hax_mod);
	PyGILState_Release(gstate);
	hax_unlock(hc);

	return broadcast_tags;
}

void m0_hax_link_stopped(unsigned long long ctx, const char *proc_ep)
{
	struct hax_context *hc = (struct hax_context *)ctx;
	struct hax_link *hxl;

	m0_tl_for(hx_links, &hc->hc_links, hxl) {
		if (m0_streq(proc_ep, hxl->hxl_ep_addr))
			hxl->hxl_is_active = false;
	} m0_tl_endfor;
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

/* ---------------------------- SNS operations ---------------------------- */

static int (*sns_action[])(struct m0_spiel *spiel,
			   const struct m0_fid *pool_fid) = {
	[CM_OP_REPAIR]            = m0_spiel_sns_repair_start,
	[CM_OP_REBALANCE]         = m0_spiel_sns_rebalance_start,
	[CM_OP_REPAIR_QUIESCE]    = m0_spiel_sns_repair_quiesce,
	[CM_OP_REBALANCE_QUIESCE] = m0_spiel_sns_rebalance_quiesce,
	[CM_OP_REPAIR_RESUME]     = m0_spiel_sns_repair_continue,
	[CM_OP_REBALANCE_RESUME]  = m0_spiel_sns_rebalance_continue,
	[CM_OP_REPAIR_ABORT]      = m0_spiel_sns_repair_abort,
	[CM_OP_REBALANCE_ABORT]   = m0_spiel_sns_rebalance_abort,
};

static int (*sns_status[])(struct m0_spiel *spiel,
			   const struct m0_fid *pool_fid,
			   struct m0_spiel_repreb_status **statuses) = {
	[CM_OP_REPAIR_STATUS]     = m0_spiel_sns_repair_status,
	[CM_OP_REBALANCE_STATUS]  = m0_spiel_sns_rebalance_status,
};

static int spiel_sns_op(enum m0_cm_op sns_copy_machine_op,
			unsigned long long ctx,
			const struct m0_fid *pool_fid,
			struct m0_spiel_repreb_status **sns_statuses)
{
	struct hax_context *hc = (struct hax_context *)ctx;
	struct m0_spiel *spiel = m0_halon_interface_spiel(hc->hc_hi);
	int rc = 0;

	M0_ENTRY();

	if (!hc->hc_alive) {
		M0_LOG(M0_WARN, "Cannot make SPIEL API call as HAX Python"
				" context has been already destructed");
		return M0_ERR(-ESHUTDOWN);
	}

	if (!hc->hc_rconfc_initialized) {
		M0_LOG(M0_WARN, "Cannot make SPIEL API call as libmotr 'rconfc'"
				" susbsystem hasn't been initialised");
		return M0_ERR(-EDESTADDRREQ);
	}

	switch (sns_copy_machine_op) {
	case CM_OP_REPAIR:
	case CM_OP_REBALANCE:
	case CM_OP_REPAIR_QUIESCE:
	case CM_OP_REBALANCE_QUIESCE:
	case CM_OP_REPAIR_RESUME:
	case CM_OP_REBALANCE_RESUME:
	case CM_OP_REPAIR_ABORT:
	case CM_OP_REBALANCE_ABORT:
		rc = sns_action[sns_copy_machine_op](spiel, pool_fid);
		break;
	case CM_OP_REPAIR_STATUS:
	case CM_OP_REBALANCE_STATUS:
		if (sns_statuses == NULL) {
			M0_LOG(M0_ERROR, "m0_spiel_repreb_status cannot be NULL"
			       " for CM_OP_REPAIR_STATUS and"
			       " CM_OP_REBALANCE_STATUS");
			rc = -EINVAL;
			break;
		}
		rc = sns_status[sns_copy_machine_op](spiel, pool_fid,
						     sns_statuses);
		break;
	default:
		M0_LOG(M0_WARN, "Unknown m0_cm_op: %u", sns_copy_machine_op);
		rc = -EINVAL;
	}

	return rc < 0 ? M0_ERR(rc) : M0_RC(rc);
}

int start_repair(unsigned long long ctx, const struct m0_fid *pool_fid)
{
	return spiel_sns_op(CM_OP_REPAIR, ctx, pool_fid, NULL);
}

int start_rebalance(unsigned long long ctx, const struct m0_fid *pool_fid)
{
	return spiel_sns_op(CM_OP_REBALANCE, ctx, pool_fid, NULL);
}

int pause_repair(unsigned long long ctx, const struct m0_fid *pool_fid)
{
	return spiel_sns_op(CM_OP_REPAIR_QUIESCE, ctx, pool_fid, NULL);
}

int pause_rebalance(unsigned long long ctx, const struct m0_fid *pool_fid)
{
	return spiel_sns_op(CM_OP_REBALANCE_QUIESCE, ctx, pool_fid, NULL);
}

int resume_repair(unsigned long long ctx, const struct m0_fid *pool_fid)
{
	return spiel_sns_op(CM_OP_REPAIR_RESUME, ctx, pool_fid, NULL);
}

int resume_rebalance(unsigned long long ctx, const struct m0_fid *pool_fid)
{
	return spiel_sns_op(CM_OP_REBALANCE_RESUME, ctx, pool_fid, NULL);
}

int stop_repair(unsigned long long ctx, const struct m0_fid *pool_fid)
{
	return spiel_sns_op(CM_OP_REPAIR_ABORT, ctx, pool_fid, NULL);
}

int stop_rebalance(unsigned long long ctx, const struct m0_fid *pool_fid)
{
	return spiel_sns_op(CM_OP_REBALANCE_ABORT, ctx, pool_fid, NULL);
}

static PyObject *spiel_sns_status(enum m0_cm_op sns_copy_machine_op,
				  unsigned long long ctx,
				  const struct m0_fid *pool_fid)
{
	struct m0_spiel_repreb_status *statuses;
	int rc, i;

	rc = spiel_sns_op(CM_OP_REPAIR_STATUS, ctx, pool_fid, &statuses);
	M0_LOG(M0_DEBUG, "number of m0_spiel_repreb_status'es received %d", rc);
	if (rc <= 0) {
		if (rc < 0)
			M0_LOG(M0_ERROR,
			       "m0_spiel_sns_{repair,rebalance}_status"
			       " error %d", rc);
		Py_RETURN_NONE;
	}

	PyGILState_STATE gstate;
	gstate = PyGILState_Ensure();

	PyObject *hax_mod = getModule("hax.types");
	PyObject *list = PyList_New(rc);

	for (i = 0; i < rc; ++i) {
		PyObject *py_fid = toFid(&statuses[i].srs_fid);
		PyObject *status = PyObject_CallMethod(
			hax_mod, "ReprebStatus", "(OKI)", py_fid,
			statuses[i].srs_state, statuses[i].srs_progress);
		PyList_SET_ITEM(list, i, status);
	}
	m0_free(statuses);

	Py_DECREF(hax_mod);
	PyGILState_Release(gstate);

	return list;
}

PyObject *repair_status(unsigned long long ctx, const struct m0_fid *pool_fid)
{
	return spiel_sns_status(CM_OP_REPAIR_STATUS, ctx, pool_fid);
}

PyObject *rebalance_status(unsigned long long ctx, const struct m0_fid *pool_fid)
{
	return spiel_sns_status(CM_OP_REBALANCE_STATUS, ctx, pool_fid);
}

#undef M0_TRACE_SUBSYSTEM

/*
 *  Local variables:
 *  c-indentation-style: "K&R"
 *  c-basic-offset: 8
 *  tab-width: 8
 *  fill-column: 80
 *  scroll-step: 1
 *  End:
 */
