#include <Python.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include "fid/fid.h"                    /* M0_FID_TINIT */
#include "ha/halon/interface.h"         /* m0_halon_interface */
#include "ha/note.h"
#include "module/instance.h"
#include "lib/assert.h"                 /* M0_ASSERT */
#include "lib/memory.h"                 /* M0_ALLOC_ARR */
#include "lib/thread.h"                 /* m0_thread_{adopt, shun} */
#include "lib/string.h"                 /* m0_strdup */
#include "lib/trace.h"                  /* M0_LOG, M0_DEBUG */
#include "mero/version.h"        // M0_VERSION_GIT_REV_ID
#include "ha/msg.h"
#include "hax.h"

static hax_context *hc;
struct m0_thread    mthread;
struct m0          *m0;

PyObject* getModule(char* module_name)
{
  PyObject* sys_mod_dict = PyImport_GetModuleDict();
  PyObject* hax_mod = PyMapping_GetItemString(sys_mod_dict, module_name);
  if (hax_mod == NULL)
  {
    PyObject *sys = PyImport_ImportModule("sys");
    PyObject *path = PyObject_GetAttrString(sys, "path");
    PyList_Append(path, PyUnicode_FromString("."));

    Py_DECREF(sys);
    Py_DECREF(path);

    PyObject* mod_name = PyUnicode_FromString(module_name);
    hax_mod = PyImport_Import(mod_name);
    Py_DECREF(mod_name);
  }
  return hax_mod;
}

PyObject* toFid(const struct m0_fid* fid)
{
  PyObject* hax_mod = getModule("hax.types");
  PyObject* instance = PyObject_CallMethod(hax_mod, "Fid", "(KK)", fid->f_container, fid->f_key);
  Py_DECREF(hax_mod);
  return instance;
}

PyObject* toUid128(const struct m0_uint128* val)
{
  PyObject* hax_mod = getModule("hax.types");
  PyObject* instance = PyObject_CallMethod(hax_mod, "Uint128", "(KK)", val->u_hi, val->u_lo);
  Py_DECREF(hax_mod);
  return instance;
}

static void entrypoint_request_cb( struct m0_halon_interface *hi
                                  , const struct m0_uint128   *req_id
                                  , const char                *remote_rpc_endpoint
                                  , const struct m0_fid       *process_fid
                                  , const char                *git_rev_id
                                  , uint64_t                   pid
                                  , bool                       first_request
                                  )
{
  struct m0_fid *confd_fids;
  const char    **confd_eps;
  const char    *rm_ep;
  // [KN] This is obligatory since we want to work with Python object and we obviously work from an external thread.
  // FYI: https://docs.python.org/2/c-api/init.html#releasing-the-gil-from-extension-code
  PyGILState_STATE gstate;
  gstate = PyGILState_Ensure();

  printf("In entrypoint_request_cb\n");
  PyObject* py_fid = toFid(process_fid);
  PyObject* py_req = toUid128(req_id);

  PyObject_CallMethod(
      hc->hc_handler,
      "_entrypoint_request_cb",
      "(OsOskb)",
      py_req,
      remote_rpc_endpoint,
      py_fid,
      git_rev_id,
      pid,
      first_request
    );
  Py_DECREF(py_req);
  Py_DECREF(py_fid);
  //
  // [KN] Note that the Python threads will get unblocked only after this call
  PyGILState_Release(gstate);

  /* Mock reply start */
  M0_ALLOC_ARR(confd_fids, 1);
  if (confd_fids == NULL) {
      M0_LOG(M0_ERROR, "fid array allocation failure");
      return;
  }
  confd_fids[0] = M0_FID_TINIT('s', 3, 1);
  M0_ALLOC_ARR(confd_eps, 1);
  if (confd_eps == NULL)
      M0_LOG(M0_ALWAYS, "confd ep array allocation failure");
  confd_eps[0] = m0_strdup("172.28.128.4@tcp:12345:44:1");
  rm_ep = m0_strdup("172.28.128.4@tcp:12345:44:1");

  /* Invoke this directly from python land after fetching relevant information from consul.*/
  m0_halon_interface_entrypoint_reply(hi, req_id, 0, 1, confd_fids, confd_eps, 1, &M0_FID_TINIT('s', 4, 1), rm_ep);
  M0_LOG(M0_ALWAYS, "Entry point replied");
  /* Mock reply end */
}

static void _failvec_reply_send(struct m0_halon_interface *hi, struct m0_ha_link *hl, struct m0_ha_msg *msg)
{
  m0_ha_failvec_reply_send(hl, msg, &M0_FID_TINIT('o', 2, 9), 0);
}

/*
 * Sends failvec reply.
 * To be invoked from Python land.
 */
void m0_ha_failvec_reply_send(struct m0_ha_link *hl, struct m0_ha_msg *msg, struct m0_fid *pool_fid,
                              uint32_t nr_notes)
{
  struct m0_ha_msg *repmsg;
  uint64_t          tag;

  M0_PRE(hl != NULL);

  M0_ALLOC_PTR(repmsg);
  if (repmsg == NULL)
      return;
  repmsg->hm_data.hed_type = M0_HA_MSG_FAILURE_VEC_REP;
  /* Fabricated poolfid, fetch the information from consul */
  repmsg->hm_data.u.hed_fvec_rep.mfp_pool = *pool_fid;
  repmsg->hm_data.u.hed_fvec_rep.mfp_cookie = msg->hm_data.u.hed_fvec_req.mfq_cookie;

  repmsg->hm_data.u.hed_fvec_rep.mfp_nr = nr_notes;
  m0_ha_link_send(hl, repmsg, &tag);
  m0_free(repmsg);
}

/* Tests hax - mero nvec reply send. */
static void _nvec_reply_send(struct m0_halon_interface *hi, struct m0_ha_link *hl, struct m0_ha_msg *msg)
{
  m0_ha_nvec_reply_send(hl, msg, NULL);
}

/*
 * Sends nvec reply.
 * To be invoked from python land.
 */
void m0_ha_nvec_reply_send(struct m0_ha_link *hl, struct m0_ha_msg *msg, struct m0_ha_nvec *nvec)
{
  const struct m0_ha_msg_nvec *nvec_req;
  struct m0_ha_nvec            _nvec;
  struct m0_fid                obj_fid;
  int                          i;

  nvec_req = &msg->hm_data.u.hed_nvec;

  /* Temp fabricated code to just test hax - mero communication */
  if (nvec == NULL) {
      M0_LOG(M0_DEBUG, "nvec nv_nr=%"PRIu32" hmvn_type=%s", _nvec.nv_nr,
             msg->hm_data.u.hed_nvec.hmnv_type == M0_HA_NVEC_SET ?  "SET" :
              msg->hm_data.u.hed_nvec.hmnv_type == M0_HA_NVEC_GET ?  "GET" :
                                                                     "UNKNOWN!");
      _nvec = (struct m0_ha_nvec){
              .nv_nr   = msg->hm_data.u.hed_nvec.hmnv_nr,
             };
      M0_ALLOC_ARR(_nvec.nv_note, _nvec.nv_nr);
      M0_ASSERT(_nvec.nv_note != NULL);
      for (i = 0; i < _nvec.nv_nr; ++i) {
           _nvec.nv_note[i] = msg->hm_data.u.hed_nvec.hmnv_arr.hmna_arr[i];
           M0_LOG(M0_DEBUG, "nv_note[%d]=(no_id="FID_F" "
                  "no_state=%"PRIu32")", i, FID_P(&_nvec.nv_note[i].no_id),
                   _nvec.nv_note[i].no_state);
      }
      if (msg->hm_data.u.hed_nvec.hmnv_type == M0_HA_NVEC_SET) {
		/* Implement me */
      } else {
           for (i = 0; i < nvec_req->hmnv_nr; ++i) {
                obj_fid = nvec_req->hmnv_arr.hmna_arr[i].no_id;
                /* Get state of the given obj from consul.
                 * Presently create a fabricated reply.
                 */
                 M0_LOG(M0_DEBUG, "obj == NULL");
                 _nvec.nv_note[i] = (struct m0_ha_note){
                                       .no_id    = obj_fid,
                                       .no_state = M0_NC_ONLINE,
			           };
                 }
        }
      nvec = &_nvec;
  }
  m0_ha_msg_nvec_send(nvec, msg->hm_data.u.hed_nvec.hmnv_id_of_get,
                      M0_HA_NVEC_SET, hl);
  if (nvec == NULL)
      m0_free(_nvec.nv_note);
}

static void msg_received_cb (struct m0_halon_interface *hi, struct m0_ha_link *hl,
                             struct m0_ha_msg *msg, uint64_t tag)
{
  struct m0_ha            *ha;
  struct m0_ha_dispatcher *hd;

  ha = m0_halon_interface_ha(hi);
  hd = m0_halon_interface_ha_dispatcher(hi);
  if (msg->hm_data.hed_type == M0_HA_MSG_FAILURE_VEC_REQ)
	_failvec_reply_send(hi, hl, msg);
  else if (msg->hm_data.hed_type == M0_HA_MSG_NVEC)
        _nvec_reply_send(hi, hl, msg);
  else {
      /* Using generic handlers for rest of the messages,
       * implement if required.
       */
      m0_ha_dispatcher_handle(hd, ha, hl, msg, tag);
  }
  M0_LOG(M0_ALWAYS, "msg received of type: %d", msg->hm_data.hed_type);
  m0_halon_interface_delivered(hi, hl, msg);
}

static void msg_is_delivered_cb (struct m0_halon_interface *hi, struct m0_ha_link *hl,
                                 uint64_t tag)
{
  // TODO Implement me
}

static void msg_is_not_delivered_cb (struct m0_halon_interface *hi, struct m0_ha_link *hl,
                                     uint64_t tag)
{
  // TODO Implement me
}

static void link_connected_cb (struct m0_halon_interface *hi, const struct m0_uint128 *req_id,
                               struct m0_ha_link *link)
{
  // TODO Implement me
}

static void link_reused_cb (struct m0_halon_interface *hi, const struct m0_uint128 *req_id,
                            struct m0_ha_link *link)
{
  // TODO Implement me
}

static void link_is_disconnecting_cb (struct m0_halon_interface *hi, struct m0_ha_link *link)
{
  // TODO Implement me
}

void link_disconnected_cb (struct m0_halon_interface *hi, struct m0_ha_link *link)
{
  // TODO Implement me
}

hax_context* init_halink(PyObject *obj, const char* node_uuid)
{
  // Since we do depend on the Python object, we don't want to let it die before us.
  Py_INCREF(obj);
  int rc;

  /*rc = m0_thread_adopt(&mthread, m0);*/
  /*if (rc != 0) {*/
     /*printf("Mero thread adoption failed: %d\n", rc);*/
     /*return NULL;*/
  /*}*/

  hc = (hax_context*) malloc(sizeof(hax_context));
  if (hc == NULL) {
    printf("\n Error: %d\n", -ENOMEM);
    return NULL;
  }

  rc = m0_halon_interface_init(&hc->hc_hi, "M0_VERSION_GIT_REV_ID",
			       "M0_VERSION_BUILD_CONFIGURE_OPTS",
			       "disable-compatibility-check", NULL);
  if (rc != 0) {
    free(hc);
    return 0;
  }
  m0_mutex_init(&hc->hc_mutex);
  M0_SET0(&mthread);
  m0 = m0_halon_interface_m0_get(hc->hc_hi);


  hc->hc_handler = obj;

  printf("Python object addr: %p\n", obj);
  printf("Python object addr2: %p\n", hc->hc_handler);
  printf("Returning: %p\n", hc);
  return  hc;
}

void destroy_halink(unsigned long long ctx)
{
  struct hax_context* hc = (struct hax_context*) ctx;
  Py_DECREF(hc->hc_handler);
  m0_mutex_fini(&hc->hc_mutex);
  m0_halon_interface_fini(hc->hc_hi);

  /*m0_thread_shun();*/
}

int start( unsigned long long ctx
         , const char *local_rpc_endpoint
         , const struct m0_fid *process_fid
         , const struct m0_fid *ha_service_fid
         , const struct m0_fid *rm_service_fid)
{
  struct hax_context        *hc = (struct hax_context*)ctx;
  struct m0_halon_interface *hi = hc->hc_hi;
  int                        rc;

  printf("Starting hax interface..\n");
  rc = m0_halon_interface_start( hi
                                 , local_rpc_endpoint
                                 , &M0_FID_TINIT('r', process_fid->f_container, process_fid->f_key)
                                 , &M0_FID_TINIT('s', ha_service_fid->f_container, ha_service_fid->f_key)
                                 , &M0_FID_TINIT('s', rm_service_fid->f_container, rm_service_fid->f_key)
                                 , entrypoint_request_cb
                                 , msg_received_cb
                                 , msg_is_delivered_cb
                                 , msg_is_not_delivered_cb
                                 , link_connected_cb
                                 , link_reused_cb
                                 , link_is_disconnecting_cb
                                 , link_disconnected_cb
                                 );
  return rc;
}

void test(unsigned long long ctx)
{
  int               rc;

  printf("Got: %llu\n", ctx);

  // ----------
  struct hax_context* hc = (struct hax_context*) ctx;
  printf("Context addr: %p\n", hc);
  printf("handler addr: %p\n", hc->hc_handler);

  printf("GOT HERE\n");

  struct m0_uint128 t = M0_UINT128(100, 500);
  struct m0_fid fid = M0_FID_INIT(20, 50);

  //m0_mutex_lock(&hc->hc_mutex);
  entrypoint_request_cb( hc->hc_hi
                       , &t
                       , "ENDP"
                       , &fid
                       , "GIT"
                       , 12345
                       , 0
      );
  //m0_mutex_unlock(&hc->hc_mutex);
}

int main(int argc, char **argv)
{
  struct m0_halon_interface *hi;
  int rc;

  rc = m0_halon_interface_init(&hi, "", "", "disable-compatibility-check", NULL);
  M0_ASSERT(rc == 0);
  rc = m0_halon_interface_start(hi, "0@lo:12345:42:100",
                                &M0_FID_TINIT('r', 1, 1),
                                &M0_FID_TINIT('s', 1, 1),
                                &M0_FID_TINIT('s', 1, 2),
                                entrypoint_request_cb, msg_received_cb, msg_is_delivered_cb, msg_is_not_delivered_cb,
                                link_connected_cb, link_reused_cb, link_is_disconnecting_cb, link_disconnected_cb);
  M0_ASSERT(rc == 0);
  m0_halon_interface_stop(hi);
  m0_halon_interface_fini(hi);
  printf("Hello world");
  return 0;
}
