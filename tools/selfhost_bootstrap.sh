#!/usr/bin/env bash
# Self-host bootstrap: nizam-new builds src/main.nz -> nizam-self.
# Supervisor: relaunches up to 3 times (survives session restarts that
# SIGKILL the tree); RSS circuit-breaker kills the build at 1450 MB so a
# runaway peak OOM-thrashes nothing (the box has 1.8 GB RAM, 8 GB swap).
set -u
ROOT=/home/red-x/code/nizam-lang/mantiq
TOOLS=/home/red-x/.local/share/nizam-tools
LOG=$TOOLS/selfhost_build.log
RSSLOG=$TOOLS/selfhost_rss.log
TARGET=$TOOLS/nizam-self
: > "$RSSLOG"
echo "=== selfhost supervisor start $(date +%H:%M:%S) ===" >> "$LOG"

for attempt in 1 2 3; do
    echo "--- attempt $attempt $(date +%H:%M:%S) ---" >> "$LOG"
    cd "$ROOT" || exit 1
    export PATH="$TOOLS/clangshim:${PATH}"
    export CPATH="${CPATH:+${CPATH}:}$HOME/.local/lib/mantiq/include"
    export LD_LIBRARY_PATH="$ROOT:${LD_LIBRARY_PATH-}"
    ulimit -s unlimited 2>/dev/null || true
    rm -rf "$ROOT/.mantiq_cache"

    "$TOOLS/nizam-new" build src/main.nz -o "$TARGET" --no-cache --lib-dir "$PWD" \
        >> "$LOG" 2>&1 &
    BUILDPID=$!
    # circuit-breaker: watch RSS, kill build at 1100 MB
    (
        while kill -0 $BUILDPID 2>/dev/null; do
            RSS=$(ps -o rss= -p $BUILDPID 2>/dev/null | tr -d ' ')
            if [ -n "$RSS" ]; then
                echo "$(date +%H:%M:%S) $RSS" >> "$RSSLOG"
                if [ "$RSS" -gt 1450000 ]; then
                    echo "$(date +%H:%M:%S) CIRCUIT-BREAK kill at ${RSS}kB" >> "$RSSLOG"
                    kill -9 $BUILDPID 2>/dev/null
                    break
                fi
            fi
            sleep 10
        done
    ) &
    MONPID=$!
    wait $BUILDPID
    RC=$?
    kill $MONPID 2>/dev/null
    echo "attempt $attempt rc=$RC" >> "$LOG"
    if [ $RC -eq 0 ] && [ -x "$TARGET" ]; then
        echo "=== SELFHOST BUILD OK $(date +%H:%M:%S) ===" >> "$LOG"
        ls -la "$TARGET" >> "$LOG"
        exit 0
    fi
    sleep 5
done
echo "=== SELFHOST BUILD FAILED (3 attempts) $(date +%H:%M:%S) ===" >> "$LOG"
exit 1
