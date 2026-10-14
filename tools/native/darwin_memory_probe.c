/* SPDX-License-Identifier: MIT
 * Administrative, bounded self-only probe; not a production launcher/sandbox.
 * Never accepts an executable from the caller. Each invocation is a fresh process.
 */
#ifdef __APPLE__
#include <dlfcn.h>
#include <errno.h>
#include <inttypes.h>
#include <libproc.h>
#include <mach/mach.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <unistd.h>

static int snapshot(const char *mode, uint64_t cap) {
    struct proc_taskinfo info;
    memset(&info, 0, sizeof(info));
    if (proc_pidinfo(getpid(), PROC_PIDTASKINFO, 0, &info, sizeof(info)) != (int)sizeof(info)) {
        perror("proc_pidinfo"); return 70;
    }
    struct rlimit inherited;
    int kind = strcmp(mode, "data") == 0 ? RLIMIT_DATA : RLIMIT_AS;
    if (getrlimit(kind, &inherited) != 0) { perror("getrlimit"); return 70; }
    printf("{\"mode\":\"%s\",\"cap_bytes\":%" PRIu64 ",\"uid\":%u,"
           "\"virtual_bytes\":%" PRIu64 ",\"resident_bytes\":%" PRIu64 ","
           "\"inherited_soft\":%" PRIu64 ",\"inherited_hard\":%" PRIu64 ",",
           mode, cap, (unsigned)getuid(), info.pti_virtual_size, info.pti_resident_size,
           (uint64_t)inherited.rlim_cur, (uint64_t)inherited.rlim_max);
    if (strcmp(mode, "as") == 0 || strcmp(mode, "data") == 0) {
        /* Never increase either inherited limit. Same cap as production policy. */
        rlim_t effective = (rlim_t)cap;
        if (inherited.rlim_cur < effective) effective = inherited.rlim_cur;
        if (inherited.rlim_max < effective) effective = inherited.rlim_max;
        struct rlimit requested = {effective, effective};
        errno = 0;
        int result = setrlimit(kind, &requested);
        int error = errno;
        printf("\"effective_cap_bytes\":%" PRIu64 ",\"admitted\":%s,\"errno\":%d,"
               "\"exec_target\":\"/usr/bin/true\"}\n",
               (uint64_t)effective, result == 0 ? "true" : "false", error);
        fflush(stdout);
        if (result != 0) return 125;
        execl("/usr/bin/true", "true", (char *)NULL);
        perror("exec true"); return 126;
    }
    if (strcmp(mode, "footprint") == 0) {
        typedef kern_return_t (*limit_fn)(mach_port_t, int, int *);
        limit_fn set_limit = (limit_fn)dlsym(RTLD_DEFAULT, "task_set_phys_footprint_limit");
        int old = -2;
        kern_return_t result = set_limit ? set_limit(mach_task_self(), (int)(cap >> 20), &old) : KERN_NOT_SUPPORTED;
        printf("\"symbol_available\":%s,\"mach_return\":%d,\"old_limit_mib\":%d,"
               "\"enforcement_verified\":false}\n", set_limit ? "true" : "false", result, old);
        return 0; /* API refusal is a measured finding, not a passing memory test. */
    }
    if (strcmp(mode, "memorystatus") == 0) {
        /* ABI of MEMORYSTATUS_CMD_SET_MEMLIMIT_PROPERTIES from XNU headers.
         * Self only, fatal active/inactive properties; no sudo/entitlements. */
        typedef int (*control_fn)(uint32_t, int32_t, uint32_t, void *, size_t);
        struct { int32_t active; uint32_t active_attr; int32_t inactive; uint32_t inactive_attr; }
            properties = {(int32_t)(cap >> 20), 1, (int32_t)(cap >> 20), 1};
        control_fn control = (control_fn)dlsym(RTLD_DEFAULT, "memorystatus_control");
        errno = 0;
        int result = control ? control(7, getpid(), 0, &properties, sizeof(properties)) : -1;
        int error = control ? errno : ENOSYS;
        printf("\"symbol_available\":%s,\"returncode\":%d,\"errno\":%d,"
               "\"enforcement_verified\":false}\n", control ? "true" : "false", result, error);
        return 0;
    }
    return 64;
}
int main(int argc, char **argv) {
    if (argc != 3 || (strcmp(argv[1], "as") && strcmp(argv[1], "data") &&
                     strcmp(argv[1], "footprint") && strcmp(argv[1], "memorystatus"))) return 64;
    char *end = NULL;
    errno = 0;
    unsigned long long cap = strtoull(argv[2], &end, 10);
    if (errno || !end || *end || (cap != 134217728ULL && cap != 2147483648ULL)) return 64;
    /* Bound probe CPU/time even where memory admission is unavailable. */
    struct rlimit cpu;
    struct rlimit core = {0, 0};
    if (getrlimit(RLIMIT_CPU, &cpu)) return 70;
    rlim_t cpu_cap = 5;
    if (cpu.rlim_cur < cpu_cap) cpu_cap = cpu.rlim_cur;
    if (cpu.rlim_max < cpu_cap) cpu_cap = cpu.rlim_max;
    cpu.rlim_cur = cpu.rlim_max = cpu_cap;
    if (setrlimit(RLIMIT_CPU, &cpu) || setrlimit(RLIMIT_CORE, &core)) return 70;
    alarm(10);
    return snapshot(argv[1], (uint64_t)cap);
}
#else
#error This investigation requires the actual macOS SDK and Darwin kernel
#endif
