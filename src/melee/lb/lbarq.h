#ifndef GALE01_014ABC
#define GALE01_014ABC

#include <stddef.h>

typedef void (*lbArqCallback)(void* arg);

void lbArq_80014BD0(unsigned int source, void* dest, size_t length,
                    lbArqCallback callback, void* callback_arg);
void lbArq_80014D2C(void);

#endif
