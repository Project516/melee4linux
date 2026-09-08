#ifndef _lbarchive_h_
#define _lbarchive_h_

#include <Runtime/platform.h>

#include <sysdolphin/baselib/forward.h>

#include <sysdolphin/baselib/archive.h>

void lbArchive_InitializeDAT(HSD_Archive* archive, void* data, size_t length);
// Alternate output pointers and symbol names, ending with a NULL pointer.
void lbArchive_LoadSections(HSD_Archive* archive, void** symbol_dst, ...);
HSD_Archive* lbArchive_LoadArchive(const char* filename);
HSD_Archive* lbArchive_LoadSymbols(const char* filename, void* symbol_dst,
                                   ...);
HSD_Archive* lbArchive_80016DBC(const char* filename, void* symbol_dst, ...);
void lbArchive_80016EFC(HSD_Archive* archive);
bool lbArchive_80016F80(HSD_Archive** dst, const char* filename);
bool lbArchive_80017040(HSD_Archive** dst, const char* filename,
                        void* symbol_dst, ...);
bool lbArchive_800171CC(HSD_Archive** dst, const char* filename,
                        void* symbol_dst, ...);
int lbArchiveRelocate(HSD_Archive* archive, u8* src, size_t file_size,
                      intptr_t base_addr);

#endif
