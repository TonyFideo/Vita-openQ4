"""Initialize the pinned VitaGL mspace profile with real mapped memory pools.

Thresholds are reservations, not desired pool sizes. Keep pool ownership
transactional and expose readiness separately from resolution fallback.
"""
from pathlib import Path

PROFILE = 'defined(HAVE_VITA3K_SUPPORT) && !defined(HAVE_CUSTOM_HEAP) && !defined(PHYCONT_ON_DEMAND)'

POOL_CODE = r'''
/* Pool setup runs before any context allocations. An unavailable pool must not
 * masquerade as configured capacity while all draws fall back to newlib.
 * Published pools have a kernel block, GXM mapping and mspace, in that order.
 */
#if defined(HAVE_VITA3K_SUPPORT) && !defined(HAVE_CUSTOM_HEAP) && !defined(PHYCONT_ON_DEMAND)
static int voq_memory_ready = 0;

static int voq_init_mspace_pools(size_t ram, size_t cdram, size_t phy, size_t dialog) {
    if (voq_memory_ready) return 1;
    const size_t requested[VGL_MEM_EXTERNAL] = { cdram, ram, phy, dialog };
    const size_t alignment[VGL_MEM_EXTERNAL] = { 256u * 1024u, 4096u, 1024u * 1024u, 4096u };
    const char *names[VGL_MEM_EXTERNAL] = { "cdram_mempool", "ram_mempool", "phycont_mempool", "cdlg_mempool" };
    const SceKernelMemBlockType types[VGL_MEM_EXTERNAL] = {
        SCE_KERNEL_MEMBLOCK_TYPE_USER_CDRAM_RW,
        has_cached_mem ? SCE_KERNEL_MEMBLOCK_TYPE_USER_RW : SCE_KERNEL_MEMBLOCK_TYPE_USER_RW_UNCACHE,
        has_cached_mem ? SCE_KERNEL_MEMBLOCK_TYPE_USER_MAIN_PHYCONT_RW : SCE_KERNEL_MEMBLOCK_TYPE_USER_MAIN_PHYCONT_NC_RW,
        has_cached_mem ? SCE_KERNEL_MEMBLOCK_TYPE_USER_MAIN_CDIALOG_RW : SCE_KERNEL_MEMBLOCK_TYPE_USER_MAIN_CDIALOG_NC_RW
    };
    SceUID ids[VGL_MEM_EXTERNAL];
    void *bases[VGL_MEM_EXTERNAL] = {0};
    void *spaces[VGL_MEM_EXTERNAL] = {0};
    size_t sizes[VGL_MEM_EXTERNAL] = {0};
    int mapped[VGL_MEM_EXTERNAL] = {0};
    void *dummy = NULL;
    SceKernelMemBlockInfo external = {0};
    int stage = 0, bank = -1, result = -1;
    for (int i = 0; i < VGL_MEM_EXTERNAL; ++i) ids[i] = -1;
    for (bank = 0; bank < VGL_MEM_EXTERNAL; ++bank) {
        if (!requested[bank]) continue;
        stage = 1;
        if (requested[bank] > SIZE_MAX - (alignment[bank] - 1)) goto fail;
        sizes[bank] = (requested[bank] + alignment[bank] - 1) & ~(alignment[bank] - 1);
        ids[bank] = sceKernelAllocMemBlock(names[bank], types[bank], sizes[bank], NULL);
        result = ids[bank];
        if (ids[bank] < 0) goto fail;
        stage = 2;
        result = sceKernelGetMemBlockBase(ids[bank], &bases[bank]);
        if (result < 0 || !bases[bank] || (uintptr_t)bases[bank] > UINTPTR_MAX - sizes[bank]) goto fail;
        stage = 3;
        result = sceGxmMapMemory(bases[bank], sizes[bank], SCE_GXM_MEMORY_ATTRIB_RW);
        if (result < 0) goto fail;
        mapped[bank] = 1;
        stage = 4;
        spaces[bank] = sceClibMspaceCreate(bases[bank], sizes[bank]);
        if (!spaces[bank]) goto fail;
    }
    bank = VGL_MEM_EXTERNAL;
    stage = 5;
#ifdef HAVE_WRAPPED_ALLOCATORS
    dummy = __real_malloc(1);
#else
    dummy = malloc(1);
#endif
    if (!dummy) goto fail;
    external.size = sizeof(external);
    result = sceKernelGetMemBlockInfoByAddr(dummy, &external);
    if (result < 0 || !external.mappedBase || !external.mappedSize ||
        (uintptr_t)external.mappedBase > UINTPTR_MAX - external.mappedSize ||
        (uintptr_t)dummy < (uintptr_t)external.mappedBase ||
        (uintptr_t)dummy - (uintptr_t)external.mappedBase >= external.mappedSize) goto fail;
    stage = 6;
    result = sceGxmMapMemory(external.mappedBase, external.mappedSize, SCE_GXM_MEMORY_ATTRIB_RW);
    if (result < 0) goto fail;
    /* Nothing after this point can fail. The dummy stays allocated through
     * the query/map; this avoids querying the ownership of a freed pointer.
     */
#ifdef HAVE_WRAPPED_ALLOCATORS
    __real_free(dummy);
#else
    free(dummy);
#endif
    for (int i = 0; i < VGL_MEM_EXTERNAL; ++i) {
        mempool_addr[i] = bases[i];
        mempool_end[i] = bases[i] ? (void *)((uintptr_t)bases[i] + sizes[i]) : NULL;
        mempool_size[i] = sizes[i];
        mempool_mspace[i] = spaces[i];
        sceClibPrintf("[VOQ4][gpu-pool] bank=%d bytes=%u base=%p active=%d\n",
            i, (unsigned)sizes[i], bases[i], spaces[i] != NULL);
    }
    mempool_addr[VGL_MEM_EXTERNAL] = external.mappedBase;
    mempool_end[VGL_MEM_EXTERNAL] = (void *)((uintptr_t)external.mappedBase + external.mappedSize);
    mempool_size[VGL_MEM_EXTERNAL] = external.mappedSize;
    vgl_has_cdlg_support = dialog == 0;
    voq_memory_ready = 1;
    return 1;
fail:
    sceClibPrintf("[VOQ4][gpu-pool] initialization failed bank=%d stage=%d result=0x%x\n",
        bank, stage, (unsigned)result);
    if (dummy) {
#ifdef HAVE_WRAPPED_ALLOCATORS
        __real_free(dummy);
#else
        free(dummy);
#endif
    }
    for (int i = VGL_MEM_EXTERNAL - 1; i >= 0; --i) {
        if (spaces[i]) sceClibMspaceDestroy(spaces[i]);
        if (mapped[i]) sceGxmUnmapMemory(bases[i]);
        if (ids[i] >= 0) sceKernelFreeMemBlock(ids[i]);
    }
    /* No partial state was published. A caller can diagnose/retry setup;
     * neither context construction nor rendering may continue on this path.
     */
    return 0;
}
#endif

int voq_vgl_memory_init_ok(void) {
#if defined(HAVE_VITA3K_SUPPORT) && !defined(HAVE_CUSTOM_HEAP) && !defined(PHYCONT_ON_DEMAND)
    return voq_memory_ready;
#else
    return 1; /* Other allocator profiles retain their original initialization. */
#endif
}
'''

THRESHOLD_CODE = r'''
/* Free-space reports need not be allocation-granule multiples. Align DOWN
 * after retaining the requested reservation; mem_init must not round beyond
 * the reported budget. The threshold is never interpreted as the pool size.
 */
static int voq_pool_size(size_t available, int reserve, size_t granule) {
    if (reserve < 0 || !granule || (granule & (granule - 1))) return -1;
    const size_t bytes = available > (size_t)reserve ? available - (size_t)reserve : 0;
    const size_t aligned = bytes & ~(granule - 1);
    if (aligned > INT_MAX) return -1;
    return (int)aligned;
}

static GLboolean voq_init_threshold(int pool_size, int width, int height, int ram_threshold,
    int cdram_threshold, int phycont_threshold, int cdlg_threshold, SceGxmMultisampleMode msaa) {
    if (ram_threshold < 0 || cdram_threshold < 0 || phycont_threshold < 0 || cdlg_threshold < 0) {
        sceClibPrintf("[VOQ4][gpu-pool] negative memory reservation rejected\n");
        return GL_FALSE;
    }
    init_gxm();
    int ram = 0, cdram = 0, phy = 0, dialog = 0, result;
    if (system_app_mode) {
        SceAppMgrBudgetInfo info = {0};
        info.size = sizeof(info);
        result = sceAppMgrGetBudgetInfo(&info);
        if (result < 0) goto fail;
        ram = voq_pool_size(info.free_user_rw, ram_threshold, 4096);
    } else {
        SceKernelFreeMemorySizeInfo info = {0};
        info.size = sizeof(info);
        result = sceKernelGetFreeMemorySize(&info);
        if (result < 0) goto fail;
        ram = voq_pool_size(info.size_user, ram_threshold, 4096);
        cdram = voq_pool_size(info.size_cdram, cdram_threshold, 256u * 1024u);
        phy = voq_pool_size(info.size_phycont, phycont_threshold, 1024u * 1024u);
        dialog = voq_pool_size(SCE_KERNEL_MAX_MAIN_CDIALOG_MEM_SIZE, cdlg_threshold, 4096);
    }
    if (ram < 0 || cdram < 0 || phy < 0 || dialog < 0) { result = -1; goto fail; }
    sceClibPrintf("[VOQ4][gpu-pool] plan ram=%d cdram=%d phy=%d dialog=%d\n", ram, cdram, phy, dialog);
    return vglInitWithCustomSizes(pool_size, width, height, ram, cdram, phy, dialog, msaa);
fail:
    sceClibPrintf("[VOQ4][gpu-pool] budget query/size failed result=0x%x\n", (unsigned)result);
    return GL_FALSE;
}
'''


def patch(root: Path) -> None:
    def once(text, old, new):
        if text.count(old) != 1:
            raise RuntimeError('memory patch anchor mismatch: ' + old[:80])
        return text.replace(old, new, 1)

    path = root / 'source/utils/mem_utils.c'
    text = path.read_text()
    marker = 'void vgl_mem_init(size_t size_ram, size_t size_cdram, size_t size_phycont, size_t size_cdlg) {'
    text = once(text, marker, POOL_CODE + '\n' + marker + '\n#if ' + PROFILE + '\n'
        '\tvoq_init_mspace_pools(size_ram, size_cdram, size_phycont, size_cdlg);\n\treturn;\n#endif\n')
    path.write_text(text)
    path = root / 'source/shared.h'
    text = path.read_text()
    text = once(text, '// Framebuffers\n', '// Framebuffers\nint voq_vgl_memory_init_ok(void);\n')
    path.write_text(text)
    path = root / 'source/vgl.c'
    text = path.read_text()
    call = '\tvgl_mem_init(ram_pool_size, cdram_pool_size, phycont_pool_size, cdlg_pool_size);'
    text = once(text, call, call + '\n\tif (!voq_vgl_memory_init_ok()) return GL_FALSE;')
    marker = 'GLboolean vglInitWithCustomThreshold(int pool_size, int width, int height, int ram_threshold, int cdram_threshold, int phycont_threshold, int cdlg_threshold, SceGxmMultisampleMode msaa) {'
    text = once(text, marker, '\n#if ' + PROFILE + '\n#include <limits.h>\n' + THRESHOLD_CODE + '\n#endif\n' + marker +
        '\n#if ' + PROFILE + '\n\treturn voq_init_threshold(pool_size, width, height, ram_threshold, cdram_threshold, phycont_threshold, cdlg_threshold, msaa);\n#endif\n')
    path.write_text(text)
    print('Applied checked, aligned and transactional native mspace pool initialization')
