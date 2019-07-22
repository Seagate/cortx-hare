#include <Python.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include "fid/fid.h"                    /* M0_FID_TINIT */
#include "ha/halon/interface.h"         /* m0_halon_interface */
#include "module/instance.h"
#include "lib/assert.h"                 /* M0_ASSERT */
#include "lib/thread.h"                 /* m0_thread_{adopt, shun} */
#include "mero/version.h"        // M0_VERSION_GIT_REV_ID
#include "hax.h"

static hax_context *hc;

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

void entrypoint_request_cb( struct m0_halon_interface *hi
                          , const struct m0_uint128   *req_id
                          , const char                *remote_rpc_endpoint
                          , const struct m0_fid       *process_fid
                          , const char                *git_rev_id
                          , uint64_t                   pid
                          , bool                       first_request
                          )
{
  /*Py_BEGIN_ALLOW_THREADS*/
  printf("Context addr: %p\n", hc);
  printf("handler addr: %p\n", hc->hc_handler);
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
  //m0_halon_interface_entrypoint_reply(hi, req_id, 0, 0, NULL, NULL, 1, M0_FID_TINIT('s', 72, 1), NULL);
  Py_DECREF(py_req);
  Py_DECREF(py_fid);

  /*Py_END_ALLOW_THREADS*/
}

void msg_received_cb ( struct m0_halon_interface *hi
                     , struct m0_ha_link         *hl
                     , const struct m0_ha_msg    *msg
                     , uint64_t                   tag
                     )
{
  // TODO Implement me
  printf("\n msg received \n");
}

void msg_is_delivered_cb ( struct m0_halon_interface *hi
                         , struct m0_ha_link         *hl
                         , uint64_t                   tag
                         ) {
  // TODO Implement me
}

void msg_is_not_delivered_cb ( struct m0_halon_interface *hi
                             , struct m0_ha_link         *hl
                             , uint64_t                   tag
                             ) {
  // TODO Implement me
}

void link_connected_cb ( struct m0_halon_interface *hi
                       , const struct m0_uint128   *req_id
                       , struct m0_ha_link         *link
                       ) {
  // TODO Implement me
}

void link_reused_cb ( struct m0_halon_interface *hi
                    , const struct m0_uint128   *req_id
                    , struct m0_ha_link         *link
                    ) {
  // TODO Implement me
}

void link_is_disconnecting_cb ( struct m0_halon_interface *hi
                              , struct m0_ha_link         *link
                              ) {
  // TODO Implement me
}

void link_disconnected_cb ( struct m0_halon_interface *hi
                          , struct m0_ha_link         *link
                          ) {
  // TODO Implement me
}

hax_context* init_halink(PyObject *obj, const char* node_uuid)
{
  // Since we do depend on the Python object, we don't want to let it die before us.
  Py_INCREF(obj);

  int rc; // Note that Py_BEGIN_ALLOW_THREADS contains an open { and defines a block.

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
}

int start( unsigned long long ctx
         , const char *local_rpc_endpoint
         , const struct m0_fid *process_fid
         , const struct m0_fid *ha_service_fid
         , const struct m0_fid *rm_service_fid)
{
  struct hax_context *hc = (struct hax_context*)ctx;
  struct m0_halon_interface* hi = hc->hc_hi;

  return m0_halon_interface_start( hi
                                 , local_rpc_endpoint
                                 , process_fid
                                 , ha_service_fid
                                 , rm_service_fid
                                 , entrypoint_request_cb
                                 , msg_received_cb
                                 , msg_is_delivered_cb
                                 , msg_is_not_delivered_cb
                                 , link_connected_cb
                                 , link_reused_cb
                                 , link_is_disconnecting_cb
                                 , link_disconnected_cb
                                 );
}

void test(unsigned long long ctx)
{
  struct m0_thread  mthread;
  struct m0        *m0;
  int               rc;

  printf("Got: %llu\n", ctx);

  // ----------
  struct hax_context* hc = (struct hax_context*) ctx;
  printf("Context addr: %p\n", hc);
  printf("handler addr: %p\n", hc->hc_handler);

  printf("GOT HERE\n");

  struct m0_uint128 t = M0_UINT128(100, 500);
  struct m0_fid fid = M0_FID_INIT(20, 50);

  M0_SET0(&mthread);
  m0 = m0_halon_interface_m0_get(hc->hc_hi);
  rc = m0_thread_adopt(&mthread, m0);
  if (rc != 0) {
     printf("Mero thread adoption failed: %d\n", rc);
     return;
  }
  m0_mutex_lock(&hc->hc_mutex);
  entrypoint_request_cb( hc->hc_hi
                       , &t
                       , "ENDP"
                       , &fid
                       , "GIT"
                       , 12345
                       , 0
      );
  m0_mutex_unlock(&hc->hc_mutex);
  m0_thread_shun();
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
