#include <tree_sitter/api.h>

void ts_tree_root_node_ptr(const TSTree *tree, TSNode *out_node) {
    *out_node = ts_tree_root_node(tree);
}

const char *ts_node_type_ptr(const TSNode *node) {
    return ts_node_type(*node);
}

uint32_t ts_node_child_count_ptr(const TSNode *node) {
    return ts_node_child_count(*node);
}

void ts_node_child_ptr(const TSNode *node, uint32_t index, TSNode *out_node) {
    *out_node = ts_node_child(*node, index);
}

uint32_t ts_node_start_byte_ptr(const TSNode *node) {
    return ts_node_start_byte(*node);
}

uint32_t ts_node_end_byte_ptr(const TSNode *node) {
    return ts_node_end_byte(*node);
}

bool ts_node_is_named_ptr(const TSNode *node) {
    return ts_node_is_named(*node);
}

char *ts_node_string_ptr(const TSNode *node) {
    return ts_node_string(*node);
}

const char *ts_node_field_name_for_child_ptr(const TSNode *node, uint32_t index) {
    return ts_node_field_name_for_child(*node, index);
}

void ts_node_named_child_ptr(const TSNode *node, uint32_t index, TSNode *out_node) {
    *out_node = ts_node_named_child(*node, index);
}

uint32_t ts_node_start_row_ptr(const TSNode *node) {
    return ts_node_start_point(*node).row;
}

uint32_t ts_node_start_col_ptr(const TSNode *node) {
    return ts_node_start_point(*node).column;
}

uint32_t ts_node_end_row_ptr(const TSNode *node) {
    return ts_node_end_point(*node).row;
}

uint32_t ts_node_end_col_ptr(const TSNode *node) {
    return ts_node_end_point(*node).column;
}

void ts_node_child_by_field_name_ptr(const TSNode *node, const char *name, uint32_t name_length, TSNode *out_node) {
    *out_node = ts_node_child_by_field_name(*node, name, name_length);
}

bool ts_node_is_null_ptr(const TSNode *node) {
    return ts_node_is_null(*node);
}

// ── Milestone D follow-up: TU-side lib-dir resolution (was runtime.c) ──
// The compiler TU declares these extern; native products did not link
// runtime.c, so the self-hosted build failed at ld with undefined
// compiler_lib_dir/set_compiler_lib_dir. Strong defs here (runtime.c
// copies are now weak) satisfy them; the shim dead-code sweep drops
// them from products that never reference them.
#include <limits.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static char g_lib_dir_override[PATH_MAX] = {0};
__attribute__((weak)) void set_compiler_lib_dir(const char* dir) {
    if (dir) {
        strncpy(g_lib_dir_override, dir, sizeof(g_lib_dir_override) - 1);
        g_lib_dir_override[sizeof(g_lib_dir_override) - 1] = '\0';
    }
}

__attribute__((weak)) const char* compiler_lib_dir(void) {
    if (g_lib_dir_override[0]) return g_lib_dir_override;
#if defined(__wasi__)
    if (access("mantiq/runtime.c", 0) == 0) return "mantiq";
    if (access("runtime.c", 0) == 0) return ".";
    if (access("../mantiq/runtime.c", 0) == 0) return "../mantiq";
    return ".";
#elif !defined(_WIN32)
    static char buf[PATH_MAX];
    char test[PATH_MAX];

    // 1. Check directory of executable (/proc/self/exe)
    ssize_t n = readlink("/proc/self/exe", buf, sizeof(buf) - 1);
    if (n > 0) {
        buf[n] = '\0';
        char* slash = strrchr(buf, '/');
        if (slash != NULL) {
            if (slash == buf) {
                slash[1] = '\0';
            } else {
                *slash = '\0';
            }
            snprintf(test, sizeof(test), "%s/runtime.c", buf);
            if (access(test, R_OK) == 0) {
                snprintf(test, sizeof(test), "%s/tree_sitter_helper.c", buf);
                if (access(test, R_OK) == 0) {
                    snprintf(test, sizeof(test), "%s/libtree-sitter-mantiq.so", buf);
                    if (access(test, R_OK) == 0) return buf;
                }
            }
        }
    }

    // 2. Check user local library: ~/.local/lib/mantiq
    const char* home = getenv("HOME");
    if (home) {
        snprintf(buf, sizeof(buf), "%s/.local/lib/mantiq", home);
        snprintf(test, sizeof(test), "%s/runtime.c", buf);
        if (access(test, R_OK) == 0) {
            snprintf(test, sizeof(test), "%s/tree_sitter_helper.c", buf);
            if (access(test, R_OK) == 0) {
                snprintf(test, sizeof(test), "%s/libtree-sitter-mantiq.so", buf);
                if (access(test, R_OK) == 0) return buf;
            }
        }
    }

    // 3. Check system wide: /usr/local/lib/mantiq
    snprintf(buf, sizeof(buf), "/usr/local/lib/mantiq");
    snprintf(test, sizeof(test), "%s/runtime.c", buf);
    if (access(test, R_OK) == 0) {
        snprintf(test, sizeof(test), "%s/tree_sitter_helper.c", buf);
        if (access(test, R_OK) == 0) {
            snprintf(test, sizeof(test), "%s/libtree-sitter-mantiq.so", buf);
            if (access(test, R_OK) == 0) return buf;
        }
    }

    // 4. Check system wide: /usr/lib/mantiq
    snprintf(buf, sizeof(buf), "/usr/lib/mantiq");
    snprintf(test, sizeof(test), "%s/runtime.c", buf);
    if (access(test, R_OK) == 0) {
        snprintf(test, sizeof(test), "%s/tree_sitter_helper.c", buf);
        if (access(test, R_OK) == 0) {
            snprintf(test, sizeof(test), "%s/libtree-sitter-mantiq.so", buf);
            if (access(test, R_OK) == 0) return buf;
        }
    }

    return NULL;
#else
    static char buf[MAX_PATH];
    char test[MAX_PATH];
    DWORD n = GetModuleFileNameA(NULL, buf, sizeof(buf) - 1);
    if (n > 0) {
        buf[n] = '\0';
        char* slash = strrchr(buf, '\\');
        if (!slash) slash = strrchr(buf, '/');
        if (slash != NULL) {
            *slash = '\0';
            snprintf(test, sizeof(test), "%s\\runtime.c", buf);
            if (_access(test, 4) == 0) return buf;
        }
    }
    const char* localapp = getenv("LOCALAPPDATA");
    if (localapp) {
        snprintf(buf, sizeof(buf), "%s\\mantiq", localapp);
        snprintf(test, sizeof(test), "%s\\runtime.c", buf);
        if (_access(test, 4) == 0) return buf;
    }
    const char* progfiles = getenv("ProgramFiles");
    if (progfiles) {
        snprintf(buf, sizeof(buf), "%s\\mantiq", progfiles);
        snprintf(test, sizeof(test), "%s\\runtime.c", buf);
        if (_access(test, 4) == 0) return buf;
    }
    return NULL;
#endif
}
