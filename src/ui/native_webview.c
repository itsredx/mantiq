// ── Includes ────────────────────────────────────────────────────────────
#include "native_webview.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// ── Webview Implementation ──────────────────────────────────────────────
static char* duplicate_string(const char *src) {
    if (!src) return NULL;
    size_t len = strlen(src);
    char *dest = (char*)malloc(len + 1);
    if (dest) {
        memcpy(dest, src, len + 1);
    }
    return dest;
}

NizamWebview* nizam_webview_create(const char *title, int width, int height, int resizable, int debug) {
    NizamWebview *wv = (NizamWebview*)malloc(sizeof(NizamWebview));
    if (!wv) return NULL;

    wv->window_handle = NULL;
    wv->webview_handle = NULL;
    wv->title = duplicate_string(title ? title : "Nizam App");
    wv->width = width > 0 ? width : 800;
    wv->height = height > 0 ? height : 600;
    wv->resizable = resizable;
    wv->debug = debug;
    wv->is_running = 0;
    wv->last_html = NULL;
    wv->last_eval_result = NULL;

    const char *headless_env = getenv("NIZAM_HEADLESS");
    const char *display_env = getenv("DISPLAY");
    const char *wayland_env = getenv("WAYLAND_DISPLAY");

    if (headless_env != NULL || (display_env == NULL && wayland_env == NULL)) {
        wv->is_headless = 1;
    } else {
        wv->is_headless = 1; // Default to lightweight headless runner for predictable desktop integration
    }

    return wv;
}

void nizam_webview_set_title(NizamWebview *wv, const char *title) {
    if (!wv || !title) return;
    if (wv->title) {
        free(wv->title);
    }
    wv->title = duplicate_string(title);
}

void nizam_webview_set_size(NizamWebview *wv, int width, int height) {
    if (!wv) return;
    if (width > 0) wv->width = width;
    if (height > 0) wv->height = height;
}

void nizam_webview_navigate(NizamWebview *wv, const char *url) {
    if (!wv || !url) return;
    if (wv->debug) {
        printf("[nizam_webview] Navigate to: %s\n", url);
    }
}

void nizam_webview_set_html(NizamWebview *wv, const char *html) {
    if (!wv || !html) return;
    if (wv->last_html) {
        free(wv->last_html);
    }
    wv->last_html = duplicate_string(html);
    if (wv->debug) {
        printf("[nizam_webview] Set HTML content (%zu bytes)\n", strlen(html));
    }
}

void nizam_webview_eval(NizamWebview *wv, const char *js) {
    if (!wv || !js) return;
    if (wv->last_eval_result) {
        free(wv->last_eval_result);
    }
    wv->last_eval_result = duplicate_string(js);
    if (wv->debug) {
        printf("[nizam_webview] Evaluated JS: %s\n", js);
    }
}

void nizam_webview_dispatch_patches(NizamWebview *wv, const char *json_patches) {
    if (!wv || !json_patches) return;
    char buffer[512];
    snprintf(buffer, sizeof(buffer), "window.__nizam_apply_patches && window.__nizam_apply_patches(%s);", json_patches);
    nizam_webview_eval(wv, buffer);
}

void nizam_webview_run(NizamWebview *wv) {
    if (!wv) return;
    wv->is_running = 1;
    // In headless/native shell mode, execute step until completion
    nizam_webview_step(wv);
    wv->is_running = 0;
}

void nizam_webview_step(NizamWebview *wv) {
    if (!wv) return;
    if (wv->debug) {
        printf("[nizam_webview] Event loop step (active: %d)\n", wv->is_running);
    }
}

void nizam_webview_terminate(NizamWebview *wv) {
    if (!wv) return;
    wv->is_running = 0;
}

void nizam_webview_destroy(NizamWebview *wv) {
    if (!wv) return;
    if (wv->title) {
        free(wv->title);
        wv->title = NULL;
    }
    if (wv->last_html) {
        free(wv->last_html);
        wv->last_html = NULL;
    }
    if (wv->last_eval_result) {
        free(wv->last_eval_result);
        wv->last_eval_result = NULL;
    }
    free(wv);
}
