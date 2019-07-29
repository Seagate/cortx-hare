#pragma once
#ifndef __HAX_H__
#define __HAX_H__

#include "lib/mutex.h"

struct m0_halon_interface;

typedef struct hax_context {
  struct m0_halon_interface *hc_hi;
  struct m0_mutex            hc_mutex;
  PyObject                  *hc_handler;
} hax_context;

struct hax_entrypoint_request {
  struct hax_context *hep_hc;
};

struct hax_msg {
  struct hax_context *hm_hc;
  struct m0_ha_link  *hm_hl;
  struct m0_ha_msg   *hm_msg;
};

hax_context* init_halink(PyObject *obj, const char* node_uuid);

void destroy_halink(unsigned long long ctx);

int start( unsigned long long ctx
          , const char *local_rpc_endpoint
          , const struct m0_fid *process_fid
          , const struct m0_fid *ha_service_fid
          , const struct m0_fid *rm_service_fid);


void test( unsigned long long ctx );
void m0_ha_entrypoint_reply_send(unsigned long long epr,
                                 const struct m0_uint128    *req_id,
                                 int                         rc,
                                 uint32_t                    confd_nr,
                                 const struct m0_fid        *confd_fid_data,
                                 const char                **confd_eps_data,
                                 uint32_t                    confd_quorum,
                                 const struct m0_fid        *rm_fid,
                                 const char                 *rm_eps);
void m0_ha_failvec_reply_send(unsigned long long hm, struct m0_fid *pool_fid,
                              uint32_t nr_notes);
void m0_ha_nvec_reply_send(unsigned long long hm);

#endif  // __HAX_H__

