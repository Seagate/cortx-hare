#include <stdio.h>
#include "lib/assert.h"                 /* M0_ASSERT */
#include "fid/fid.h"                    /* M0_FID_TINIT */
#include "ha/halon/interface.h"         /* m0_halon_interface */


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
