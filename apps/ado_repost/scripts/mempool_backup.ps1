param(
  [string]$Out = "mempool_backup.jsonl"
)

$env:SHARED_MEMORY_NAMESPACE = "ado-repost"
$env:SHARED_MEMORY_SQLITE_PATH = (Join-Path $PSScriptRoot "..\data\shared_mempool.db")
$env:PYTHONPATH = (Join-Path $PSScriptRoot "..\..\..\libs\shared_memory\src") + ";" + $env:PYTHONPATH

python -m shared_memory.cli backup --out $Out
