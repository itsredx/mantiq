// ── Header Guard ────────────────────────────────────────────────────────
#ifndef NIZAM_NATIVE_WEBVIEW_H
#define NIZAM_NATIVE_WEBVIEW_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── Types ───────────────────────────────────────────────────────────────
typedef struct NizamWebview NizamWebview;
typedef void (*NizamWebviewCallback)(NizamWebview *wv, const char *arg, void *userdata);

struct NizamWebview {
    void *window_handle;
    void *webview_handle;
    char *title;
    int width;
    int height;
    int resizable;
    int debug;
    int is_running;
    int is_headless;
    char *last_html;
    char *last_eval_result;
};

// ── Lifecycle & Configuration ───────────────────────────────────────────
NizamWebview* nizam_webview_create(const char *title, int width, int height, int resizable, int debug);
void nizam_webview_set_title(NizamWebview *wv, const char *title);
void nizam_webview_set_size(NizamWebview *wv, int width, int height);

// ── Navigation & Scripting ──────────────────────────────────────────────
void nizam_webview_navigate(NizamWebview *wv, const char *url);
void nizam_webview_set_html(NizamWebview *wv, const char *html);
void nizam_webview_eval(NizamWebview *wv, const char *js);
void nizam_webview_dispatch_patches(NizamWebview *wv, const char *json_patches);

// ── Event Loop & Teardown ───────────────────────────────────────────────
void nizam_webview_run(NizamWebview *wv);
void nizam_webview_step(NizamWebview *wv);
void nizam_webview_terminate(NizamWebview *wv);
void nizam_webview_destroy(NizamWebview *wv);

#ifdef __cplusplus
}
#endif

#endif // NIZAM_NATIVE_WEBVIEW_H
