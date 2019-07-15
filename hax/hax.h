#pragma once
#ifndef __HAX_H__
#define __HAX_H__

struct m0_halon_interface;

typedef struct hax_context {
  struct m0_halon_interface hi;
  PyObject* handler;
} hax_context;

hax_context* init_halink(PyObject *obj, const char* node_uuid);

void destroy_halink(unsigned long long ctx);

int start( unsigned long long ctx
          , const char *local_rpc_endpoint
          , const struct m0_fid *process_fid
          , const struct m0_fid *ha_service_fid
          , const struct m0_fid *rm_service_fid);


void test( unsigned long long ctx );

#endif  // __HAX_H__

