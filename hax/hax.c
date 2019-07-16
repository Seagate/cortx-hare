#include "fid/fid.h"                    /* M0_FID_TINIT */
#include "ha/halon/interface.h"         /* m0_halon_interface */
#include "lib/assert.h"                 /* M0_ASSERT */
#include "mero/version.h"        // M0_VERSION_GIT_REV_ID
#include <Python.h>
#include <stdio.h>
#include <stdlib.h>
#include "hax.h"

PyObject* getModule(const char* module_name)
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

void entrypoint_request_cb( struct m0_halon_interface         *hi
                          , const struct m0_uint128           *req_id
                          , const char             *remote_rpc_endpoint
                          , const struct m0_fid               *process_fid
                          , const char                        *git_rev_id
                          , uint64_t                           pid
                          , bool                               first_request
                          ) {
  /*Py_BEGIN_ALLOW_THREADS*/
  struct hax_context* hax = (struct hax_context*) hi;
  PyObject* py_fid = toFid(process_fid);
  PyObject* py_req = toUid128(req_id);
  
  PyObject_CallMethod(
      hax->handler,
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

  /*Py_END_ALLOW_THREADS*/
}

void msg_received_cb ( struct m0_halon_interface *hi
                     , struct m0_ha_link         *hl
                     , const struct m0_ha_msg    *msg
                     , uint64_t                   tag
                     ) {
  // TODO Implement me
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
  struct m0_halon_interface* hi;
  // Since we do depend on the Python object, we don't want to let it die before us.
  Py_INCREF(obj);

  // [KN] Debug stuff. In real life we don't need this assignment (this happens inside m0_halon_interface_init)
  /*hi = calloc(1, sizeof(struct m0_halon_interface));*/

  int rc; // Note that Py_BEGIN_ALLOW_THREADS contains an open { and defines a block.
  //
  // TODO investigate why it doesn't work
  /*Py_BEGIN_ALLOW_THREADS*/
  rc = m0_halon_interface_init(
      &hi,
      M0_VERSION_GIT_REV_ID,
      M0_VERSION_BUILD_CONFIGURE_OPTS,
      NULL,
      node_uuid);
  /*Py_END_ALLOW_THREADS*/

  if (rc != 0)
  {
    free(hi);
    return 0;
  }


  printf("I'm here\n");
  hax_context* newp = (hax_context*) realloc(hi, sizeof(hax_context));
  if (newp == 0)
  {
    m0_halon_interface_fini(hi);
    return 0;
  }

  newp->handler = obj;

  printf("Python object addr: %p\n", obj);
  printf("Python object addr2: %p\n", newp->handler);
  printf("Returning: %p\n", newp);
  return  newp;
}

void destroy_halink(unsigned long long ctx)
{
  struct hax_context* hax = (struct hax_context*) ctx;
  Py_DECREF(hax->handler);
  m0_halon_interface_fini(&(hax->hi));
}

int start( unsigned long long ctx
         , const char *local_rpc_endpoint
         , const struct m0_fid *process_fid
         , const struct m0_fid *ha_service_fid
         , const struct m0_fid *rm_service_fid)
{
  /*printf("Received fid: {%llu, %llu}\n", process_fid->f_container, process_fid->f_key);*/
  struct m0_halon_interface* hi = (struct m0_halon_interface*) ctx;
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
  printf("Got: %llu\n", ctx);

  // ----------
  struct hax_context* hax = (struct hax_context*) ctx;
  printf("Context addr: %p\n", hax);
  printf("handler addr: %p\n", hax->handler);

  printf("GOT HERE\n");

  struct m0_halon_interface* hi = &hax->hi;

  struct m0_uint128 t = M0_UINT128(100, 500);
  struct m0_fid fid = M0_FID_INIT(20, 50);
  entrypoint_request_cb( hi
                       , &t
                       , "ENDP"
                       , &fid
                       , "GIT"
                       , 12345
                       , 0
      );

}

int main(int argc, char **argv)
{
  struct m0_halon_interface *hi;
  int rc;

  rc = m0_halon_interface_init(&hi, "", "", NULL, NULL);
  M0_ASSERT(rc == 0);
  rc = m0_halon_interface_start(hi, "0@lo:12345:42:100",
                                &M0_FID_TINIT('r', 1, 1),
                                &M0_FID_TINIT('s', 1, 1),
                                &M0_FID_TINIT('s', 1, 2),
                                NULL, NULL, NULL, NULL,
                                NULL, NULL, NULL, NULL);
  M0_ASSERT(rc == 0);
  m0_halon_interface_stop(hi);
  m0_halon_interface_fini(hi);
  printf("Hello world");
  return 0;
}
