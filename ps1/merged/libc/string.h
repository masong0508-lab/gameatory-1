/* Milestone B: the libc headers Stunt Fox includes, for its native PS1 build (no libc is linked: sfmem.c) */
#ifndef SF_STRING_H
#define SF_STRING_H
typedef unsigned int size_t;
void *memcpy(void *, const void *, size_t);
void *memset(void *, int, size_t);
int memcmp(const void *, const void *, size_t);
size_t strlen(const char *);
void *memmove(void *, const void *, size_t);
#endif
