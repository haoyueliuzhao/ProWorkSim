"""Pinned official DeepSeek V4.1 rendering/tokenization, entirely offline.

The public recipe is a provider approximation until neutral live usage agrees;
its output is never mislabeled as a server-issued exact token count. An explicit
engineering margin may be frozen by the experiment. Monetary reservations use
the provider's complete context limit independently of this local counter.
"""
from __future__ import annotations

import copy
import hashlib
import importlib
from pathlib import Path
import sys
import threading

from .storage import digest, json_bytes, read_json

VERSION = "software-benchmark-v055-official-recipe-counter-r1"


def _check_file(reference):
    path = Path(reference["path"]).resolve()
    data = path.read_bytes()
    if len(data) != reference["bytes"] or hashlib.sha256(data).hexdigest() != reference["sha256"]:
        raise ValueError("Official tokenizer/recipe artifact no longer matches its frozen manifest")
    return path


class OfficialDeepSeekCounter:
    def __init__(self, manifest_path, *, manifest_sha256, reservation_margin_tokens=128):
        if type(reservation_margin_tokens) is not int or not 0 <= reservation_margin_tokens <= 1024:
            raise ValueError("Freeze a nonnegative margin of at most 1024 tokens")
        manifest_path = Path(manifest_path).resolve()
        manifest_bytes = manifest_path.read_bytes()
        if hashlib.sha256(manifest_bytes).hexdigest() != manifest_sha256:
            raise ValueError("Tokenizer manifest SHA256 mismatch")
        manifest = read_json(manifest_path)
        if (manifest["version"] != "software-benchmark-v055-official-tokenizer-preparation-r1"
                or manifest["recipe_version"] != "0.2.0"
                or manifest["tokenizer_model"] != "deepseek-ai/DeepSeek-V4.1-Flash-1017"):
            raise ValueError("Unexpected official recipe/model preparation")
        for reference in manifest["installed_files"]:
            _check_file(reference)
        tokenizer_references = [item for item in manifest["tokenizer_files"]
                                if Path(item["path"]).name == "tokenizer.json"]
        if len(tokenizer_references) != 1:
            raise ValueError("One frozen tokenizer.json is required")
        tokenizer_path = _check_file(tokenizer_references[0])
        overlay = Path(manifest["overlay_path"]).resolve()
        if str(overlay) not in sys.path:
            sys.path.insert(0, str(overlay))
        recipe = importlib.import_module("deepseek_recipe")
        if not Path(recipe.__file__).resolve().is_relative_to(overlay):
            raise ValueError("Another recipe package is already imported; isolated overlay required")
        tokenizer = recipe.Tokenizer.from_file(str(tokenizer_path))
        self.encoding = recipe.DeepseekV41Encoding().with_tokenizer(tokenizer)
        self.recipe = recipe
        self.margin = reservation_margin_tokens
        self.manifest_sha256 = manifest_sha256
        self.tokenizer_sha256 = tokenizer_references[0]["sha256"]
        self.cache = {}
        self.lock = threading.Lock()

    def measure(self, request):
        if request.get("model") != "deepseek-flash":
            raise ValueError("Only the frozen provider model alias is accepted")
        request_sha = digest(json_bytes(request))
        with self.lock:
            if request_sha in self.cache:
                return copy.deepcopy(self.cache[request_sha])
            local = copy.deepcopy(request)
            # 0.2.0 accepts canonical model names; the official API uses this alias.
            # This changes only model identification, never messages/tools/thinking.
            local["model"] = "DeepSeek-V4.1-Flash"
            converted = self.recipe.ChatCompletionRequest(local).convert(self.recipe.ConversionOptions())
            ids = self.encoding.encode(converted.conversation)
            if not isinstance(ids, list) or not ids or any(type(value) is not int for value in ids):
                raise ValueError("Official recipe returned invalid token IDs")
            result = {
                "version": VERSION,
                "method": "official_deepseek_recipe_0.2.0_v41_with_frozen_engineering_margin",
                "backend": "DeepseekV41Encoding.encode_1017_tokenizer",
                "request_sha256": request_sha,
                "prompt_tokens": len(ids) + self.margin,
                "local_encoded_prompt_tokens": len(ids),
                "reservation_margin_tokens": self.margin,
                "token_ids_sha256": digest(json_bytes(ids)),
                "tokenizer_sha256": self.tokenizer_sha256,
                "tokenizer_manifest_sha256": self.manifest_sha256,
                "provider_model_alias": "deepseek-flash",
                "recipe_canonical_model": "DeepSeek-V4.1-Flash",
                "exact_provider_token_count": False,
                "server_usage_is_authoritative": True,
                "model_weight_loads": 0, "network_requests": 0,
            }
            self.cache[request_sha] = result
            return copy.deepcopy(result)

    __call__ = measure


def build_counter(config):
    return OfficialDeepSeekCounter(
        config["manifest_path"], manifest_sha256=config["manifest_sha256"],
        reservation_margin_tokens=config.get("reservation_margin_tokens", 128))
