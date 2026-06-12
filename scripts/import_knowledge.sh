#!/bin/sh
set -eu

INPUT_PATH="${KNOWLEDGE_CHUNKS_PATH:-knowledge_pipeline/output/chunks.jsonl}"
MODE="${KNOWLEDGE_IMPORT_MODE:-append}"
BATCH_SIZE="${KNOWLEDGE_IMPORT_BATCH_SIZE:-32}"

if [ ! -f "$INPUT_PATH" ]; then
  echo "Knowledge chunks file not found: $INPUT_PATH" >&2
  echo "Generate it with knowledge_pipeline/knowledge_batch_processor.py or mount it into the container." >&2
  exit 1
fi

python knowledge_pipeline/import_chunks_to_kb.py \
  --input "$INPUT_PATH" \
  --mode "$MODE" \
  --batch-size "$BATCH_SIZE" \
  --verbose
