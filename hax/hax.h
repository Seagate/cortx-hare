#pragma once
#ifndef __HAX_H__
#define __HAX_H__

struct m0_halon_interface;

typedef struct hax_context {
  struct m0_halon_interface hi;
  PyObject* handler;
} hax_context;

long init_halink(PyObject *obj);

void destroy_halink(long ctx);

int start( long ctx
          , const char *local_rpc_endpoint
          , const struct m0_fid *process_fid
          , const struct m0_fid *ha_service_fid
          , const struct m0_fid *rm_service_fid);


#endif  // __HAX_H__

