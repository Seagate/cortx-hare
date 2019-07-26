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

hax_context* init_halink(PyObject *obj, const char* node_uuid);

void destroy_halink(unsigned long long ctx);

int start( unsigned long long ctx
          , const char *local_rpc_endpoint
          , const struct m0_fid *process_fid
          , const struct m0_fid *ha_service_fid
          , const struct m0_fid *rm_service_fid);


void test( unsigned long long ctx );

void m0_ha_failvec_reply_send(struct m0_ha_link *hl, struct m0_ha_msg *msg, struct m0_fid *pool_fid, uint32_t nr_notes);
void m0_ha_nvec_reply_send(struct m0_ha_link *hl, struct m0_ha_msg *msg, struct m0_ha_nvec *nvec);

#endif  // __HAX_H__

