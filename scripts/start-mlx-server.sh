#!/bin/bash
# To run: ./scripts/start-mlx-server.sh
# Start MLX LM server for local model inference (requires Apple Silicon Mac)
# Test: curl http://localhost:8888/v1/chat/completions -H 'Content-Type: application/json' \
#   -d '{"messages":[{"role":"user","content":"hi"}]}'

set -e

export MLX_METAL_PREWARM=1

MODEL="${MLX_MODEL:-mlx-community/Qwen2.5-14B-Instruct-4bit}"
PORT="${MLX_PORT:-8888}"

if ! command -v mlx_lm.server &> /dev/null; then
    echo "mlx-lm not found. Installing..."
    uv pip install mlx-lm
fi

echo "Starting MLX LM server..."
echo "  Model: $MODEL"
echo "  Port:  $PORT"
echo ""
echo "Test with:"
echo "  curl http://localhost:${PORT}/v1/chat/completions -H 'Content-Type: application/json' -d '{\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}]}'"
echo ""

mlx_lm.server \
    --model "$MODEL" \
    --port "$PORT" \
    --max-tokens 4096 \
    --prefill-step-size 4096 \
    --prompt-cache-size 4 \
    --log-level DEBUG
