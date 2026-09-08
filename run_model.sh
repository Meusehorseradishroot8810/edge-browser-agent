#!/data/data/com.termux/files/usr/bin/bash
# usage: ./run_model.sh <gguf file in ~/models> "<label>" <log name> [runs]
F="$1"; LABEL="$2"; LOGN="$3"; N="${4:-10}"
for p in /proc/[0-9]*; do c=$(tr '\0' ' ' < $p/cmdline 2>/dev/null); case "$c" in *llama-server*) kill $(basename $p) 2>/dev/null;; esac; done
sleep 3
./llama.cpp/build/bin/llama-server -m "models/$F" -c 4096 -t 4 --port 8080 --jinja --log-disable > /dev/null 2>&1 &
sleep 30
sed -i "s|^MODEL = .*|MODEL = \"$LABEL (llama.cpp, local)\"|; s|^LOG = .*|LOG = \"logs/$LOGN.jsonl\"|" agent.py
python -m py_compile agent.py && echo SYNTAX_OK || exit 1
for i in $(seq 1 $N); do echo "===== RUN $i ====="; python hdr.py; python agent.py 2>&1 | grep -E "NON-JSON|RESULT|CHECKS|ERROR|Model:"; done
