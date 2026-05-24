"""Runtime utilities shared across the processing pipeline.

Provides logging setup, memory diagnostics, GPU introspection, vLLM
server health checks, span-offset computation, and a summary-quality
heuristic used by the multi-turn conversation runners.
"""

import sys
import logging
import psutil
import os
from typing import Any, Optional

def setup_logger(log_file: str = "processing.log") -> logging.Logger:
    """Create a logger that writes to both a file and stdout.

    Configures the ``MessyTextProcessor`` logger with INFO level, and
    sets the ``httpx`` logger to WARNING so retry attempts are visible
    without flooding success messages.

    Args:
        log_file: Path to the log file on disk. Defaults to
            ``"processing.log"``.

    Returns:
        The configured ``MessyTextProcessor`` logger instance.
    """
    logger = logging.getLogger("MessyTextProcessor")
    logger.setLevel(logging.INFO)
    
    # File handler (persists logs)
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    
    # Stream handler (for stdout/slurm output)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    
    logger.addHandler(fh)
    logger.addHandler(sh)

    # Configure httpx logger to show retries (WARNING to suppress success logs)
    httpx_logger = logging.getLogger("httpx")
    httpx_logger.setLevel(logging.WARNING)
    httpx_logger.addHandler(fh)
    httpx_logger.addHandler(sh)

    return logger

def log_memory_usage(logger: logging.Logger, context: str = "") -> None:
    """Log the current RSS memory usage of this process in MB.

    Args:
        logger: Logger instance to write the INFO message to.
        context: Optional label prepended to the log line (e.g.
            ``"after loading CSV"``).
    """
    process = psutil.Process(os.getpid())
    mem_mb = process.memory_info().rss / (1024 * 1024)
    logger.info(f"[Memory] {context}: {mem_mb:.2f} MB")

def get_deep_size(obj: Any, seen=None) -> int:
    """Recursively compute the total memory footprint of *obj* in bytes.

    Traverses dicts, lists, and other iterables, tracking already-visited
    object ids to avoid double-counting in cyclic structures.

    Args:
        obj: The Python object to measure.
        seen: Internal set of already-visited ``id()`` values. Callers
            should omit this argument.

    Returns:
        Approximate total size in bytes, including all reachable children.
    """
    size = sys.getsizeof(obj)
    if seen is None:
        seen = set()
    obj_id = id(obj)
    if obj_id in seen:
        return 0
    seen.add(obj_id)
    if isinstance(obj, dict):
        size += sum([get_deep_size(v, seen) for v in obj.values()])
        size += sum([get_deep_size(k, seen) for k in obj.keys()])
    elif hasattr(obj, '__iter__') and not isinstance(obj, (str, bytes, bytearray)):
        size += sum([get_deep_size(i, seen) for i in obj])
    return size


def check_gpu_info(logger: logging.Logger):
    """Query ``nvidia-smi`` for GPU hardware details and log each device.

    Args:
        logger: Logger instance for per-GPU INFO lines and WARNING on
            failure.

    Returns:
        A list of dicts (one per GPU) with keys ``id``, ``name``,
        ``total_memory_mb``, ``used_memory_mb``, ``free_memory_mb``, and
        ``utilization_pct``, or ``None`` when no GPU is detected or the
        command fails.
    """
    import subprocess
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu',
             '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            logger.warning(f"nvidia-smi failed: {result.stderr.strip()}")
            return None
        
        gpu_info = []
        for line in result.stdout.strip().split('\n'):
            if not line.strip():
                continue
            parts = [p.strip() for p in line.split(',')]
            info = {
                'id': int(parts[0]),
                'name': parts[1],
                'total_memory_mb': float(parts[2]),
                'used_memory_mb': float(parts[3]),
                'free_memory_mb': float(parts[4]),
                'utilization_pct': float(parts[5]) if parts[5] != '[N/A]' else 0
            }
            gpu_info.append(info)
            logger.info(f"GPU {info['id']}: {info['name']} | "
                       f"Memory: {info['used_memory_mb']:.0f}/{info['total_memory_mb']:.0f} MB used | "
                       f"Utilization: {info['utilization_pct']:.0f}%")
        
        return gpu_info if gpu_info else None
    except FileNotFoundError:
        logger.warning("nvidia-smi not found")
        return None
    except Exception as e:
        logger.warning(f"GPU check failed: {e}")
        return None


def check_vllm_server(client, expected_model: str, logger: logging.Logger):
    """Verify vLLM server connectivity, model availability, and inference.

    Lists available models, checks that *expected_model* is among them,
    and sends a trivial ``1+1`` completion as a smoke test.

    Args:
        client: A synchronous ``OpenAI`` client pointed at the vLLM
            endpoint.
        expected_model: Model identifier that must appear in the server's
            model list.
        logger: Logger for per-step INFO/ERROR messages.

    Returns:
        A 3-tuple ``(success, available_models, test_result)`` where
        *success* is ``True`` only when all three checks pass,
        *available_models* lists every model id reported by the server,
        and *test_result* is the raw completion text (or ``None`` on
        failure).
    """
    available_models = []
    
    # 1. List available models (from notebook: client.models.list())
    try:
        models = client.models.list()
        for model in models.data:
            available_models.append(model.id)
            logger.info(f"vLLM available model: {model.id}")
    except Exception as e:
        logger.error(f"Cannot connect to vLLM server: {e}")
        return False, [], None
    
    # 2. Check if expected model is available
    if expected_model not in available_models:
        logger.error(f"Expected model '{expected_model}' not in available models: {available_models}")
        return False, available_models, None
    
    # 3. Test request (from notebook: 1+1 test)
    try:
        response = client.chat.completions.create(
            model=expected_model,
            messages=[{'role': 'user', 'content': 'What is 1+1? Reply with just the number.'}],
            max_tokens=10,
            temperature=0.0
        )
        test_result = response.choices[0].message.content.strip()
        logger.info(f"vLLM test request successful: 1+1 = {test_result}")
        return True, available_models, test_result
    except Exception as e:
        logger.error(f"vLLM test request failed: {e}")
        return False, available_models, None


def compute_span_offsets(
    summary_by_item: dict,
    get_source_text: callable,
) -> dict:
    """
    Compute character offsets for extracted spans by searching in source documents.

    This is a post-hoc utility that enriches summary_by_item with offset information
    for traceback to original text positions.

    Args:
        summary_by_item (dict): Dictionary mapping label keys to lists of span items.
            Expected format: {
                "<label_key>": [
                    {"span": "<exact text>", "doc_id": "<id>"},
                    ...
                ]
            }
        get_source_text (callable): Function that takes a doc_id and returns the
            source text string. Signature: (doc_id: Any) -> str

    Returns:
        dict: The same structure with 'offset' added to each span item.
            Offset is -1 if span not found in source text.

    Example:
        >>> def get_source(doc_id):
        ...     sources = {"doc1": "Abel soñaba ser músico."}
        ...     return sources.get(doc_id, "")
        >>> summary_by_item = {
        ...     "vic_grupo_social": [{"span": "músico", "doc_id": "doc1"}]
        ... }
        >>> result = compute_span_offsets(summary_by_item, get_source)
        >>> result["vic_grupo_social"][0]["offset"]
        16
    """
    if not summary_by_item:
        return summary_by_item

    for label, spans in summary_by_item.items():
        if not isinstance(spans, list):
            continue
        for item in spans:
            if not isinstance(item, dict):
                continue
            span_text = item.get("span", "")
            doc_id = item.get("doc_id")
            if span_text and doc_id is not None:
                try:
                    source = get_source_text(doc_id)
                    item["offset"] = source.find(span_text) if source else -1
                except Exception:
                    item["offset"] = -1
            else:
                item["offset"] = -1

    return summary_by_item