#include "fid/fid.h"                    /* M0_FID_TINIT */
#include "ha/halon/interface.h"         /* m0_halon_interface */
#include "lib/assert.h"                 /* M0_ASSERT */
#include "mero/version.h"        // M0_VERSION_GIT_REV_ID
#include <Python.h>
#include <stdio.h>
#include <stdlib.h>
#include "hax.h"

PyObject* toFid(const struct m0_fid* fid)
{
  PyObject* sys_mod_dict = PyImport_GetModuleDict();
  PyObject* hax_mod = PyMapping_GetItemString(sys_mod_dict, "hax.types");
  PyObject* instance = PyObject_CallMethod(hax_mod, "Fid", "KK", fid->f_container, fid->f_key, NULL);
  return instance;
}

PyObject* toUid128(const struct m0_uint128* val)
{
  PyObject* sys_mod_dict = PyImport_GetModuleDict();
  PyObject* hax_mod = PyMapping_GetItemString(sys_mod_dict, "hax.types");
  PyObject* instance = PyObject_CallMethod(hax_mod, "Uint128", "KK", val->u_hi, val->u_lo, NULL);
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
  struct hax_context* hax = (struct hax_context*) hi;
  PyObject_CallMethod(
      hax->handler,
      "_entrypoint_request_cb",
      "ososkb",
      toUid128(req_id),
      remote_rpc_endpoint,
      toFid(process_fid),
      git_rev_id,
      pid,
      first_request
    );
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

long init_halink(PyObject *obj)
{
  struct m0_halon_interface* hi;
  int rc = m0_halon_interface_init(
      &hi,
      M0_VERSION_GIT_REV_ID,
      M0_VERSION_BUILD_CONFIGURE_OPTS,
      NULL,
      NULL);

  if (rc != 0)
  {
    free(hi);
    return 0;
  }

  hax_context* newp = (hax_context*) realloc(hi, sizeof(hax_context));
  if (newp == 0)
  {
    m0_halon_interface_fini(hi);
    return 0;
  }

  newp->handler = obj;
  return (long) newp;
}

void destroy_halink(long ctx)
{
  struct m0_halon_interface* hi = (struct m0_halon_interface*) ctx;
  m0_halon_interface_fini(hi);
}

int start( long ctx
          , const char *local_rpc_endpoint
          , const struct m0_fid *process_fid
          , const struct m0_fid *ha_service_fid
          , const struct m0_fid *rm_service_fid)
{
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
