#!/data/data/com.termux/files/usr/bin/bash
# usage: ./fleet_run.sh [gguf file in ~/models] [runs]
# same server flags as run_model.sh (-c 4096 -t 4) so results compare across devices
cd ~
F="${1:-qwen3-0.6b-Q4_K_M.gguf}"; N="${2:-10}"
DEV=$(getprop ro.product.model | tr ' /' '__')
DATE=$(date +%Y-%m-%d)
LABEL="${F%%.gguf}"
mkdir -p logs

for p in /proc/[0-9]*; do c=$(tr '\0' ' ' < $p/cmdline 2>/dev/null); case "$c" in *llama-server*) kill $(basename $p) 2>/dev/null;; esac; done
sleep 3
./llama.cpp/build/bin/llama-server -m "models/$F" -c 4096 -t 4 --port 8080 --jinja --log-disable > /dev/null 2>&1 &
sleep 30
curl -s localhost:8080/health || { echo "SERVER NOT UP"; exit 1; }

cat > "logs/ENV_${DEV}.json" <<EOF
{
  "device": "$(getprop ro.product.model)",
  "brand": "$(getprop ro.product.brand)",
  "android": "$(getprop ro.build.version.release)",
  "sdk": "$(getprop ro.build.version.sdk)",
  "soc": "$(getprop ro.hardware)",
  "cpu_cores": $(nproc),
  "mem_total_kb": $(grep MemTotal /proc/meminfo | awk '{print $2}'),
  "termux_version": "$TERMUX_VERSION",
  "llama_cpp_commit": "$(git -C llama.cpp rev-parse --short HEAD)",
  "model": "$F",
  "model_md5": "$(md5sum models/$F | cut -d' ' -f1)",
  "server_flags": "-c 4096 -t 4 --jinja",
  "runs_per_task": $N,
  "date": "$DATE"
}
EOF
cat "logs/ENV_${DEV}.json"

run_task () {
  SCRIPT="$1"; TASK="$2"
  LOGN="${DEV}_${TASK}_${LABEL}_${DATE}"
  sed -i "s|^LOG = .*|LOG = \"logs/$LOGN.jsonl\"|" "$SCRIPT"
  grep -q '^MODEL = "' "$SCRIPT" && sed -i "s|^MODEL = \".*|MODEL = \"$LABEL (llama.cpp, local, $DEV)\"|" "$SCRIPT"
  python -m py_compile "$SCRIPT" && echo "SYNTAX_OK $SCRIPT" || exit 1
  for i in $(seq 1 $N); do
    echo "===== $DEV $TASK RUN $i/$N ====="
    python hdr.py
    python "$SCRIPT" 2>&1 | grep -E "NON-JSON|RESULT|CHECKS|ERROR|Model:"
  done
}

run_task agent.py task1
run_task wiki.py wiki

for p in /proc/[0-9]*; do c=$(tr '\0' ' ' < $p/cmdline 2>/dev/null); case "$c" in *llama-server*) kill $(basename $p) 2>/dev/null;; esac; done

OUT="fleet_${DEV}_${DATE}.tgz"
tar czf "$OUT" logs/ENV_${DEV}.json logs/${DEV}_*.jsonl
cp "$OUT" ~/storage/downloads/ && echo "SAVED ~/storage/downloads/$OUT"
