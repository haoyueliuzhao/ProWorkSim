"""Sealed, ordered unit-weight leaf gradients for one frozen update boundary.

For fixed actor/critic parameters, advantages and original targets, composition
weights multiply the actor objective linearly. Reusing leaf gradients therefore
preserves that real-arithmetic objective. It is NOT a claim of bitwise equality
to multiplying the loss before backward: mixed-precision backward can round at
different points. Keep this execution version distinct from the old updater.

The caller owns the numerical qualification gate and must bind the full common
state (including both optimizers/RNG), recipe, source, original material, row
order, denominators and frozen advantages. This module checks exact supplied
bindings and tensor integrity; it cannot certify that those bindings are true.
It never clips gradients or calls an optimizer. Those operations belong AFTER
composition, separately for each candidate restored from the same common.
"""
from __future__ import annotations

import copy
import hashlib
import io
import math
from pathlib import Path

from .storage import atomic_write, digest, json_bytes, read_json

VERSION = "ordered-unit-gradient-bank-v0.37"
WEIGHTED_VERSION = "exact-weight-gradient-cache-v0.37"
SCOPE = ("Ordered original-decision unit-weight leaf-gradient composition; equal real-arithmetic "
         "objective, not bitwise equivalence to loss-weighted mixed-precision backward. "
         "Global clipping and restored-state optimizer steps must follow full composition.")


def _sha_file(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def _bindings(binding, rows):
    if not isinstance(binding, dict) or not binding:
        raise ValueError("A nonempty complete common/material/numerical binding is required")
    if not isinstance(rows, list) or not rows or any(not isinstance(row, dict) or not row for row in rows):
        raise ValueError("Bind every original admitted decision in a nonempty ordered row list")
    # Also reject NaN, infinity and non-JSON provenance before writing anything.
    json_bytes(binding)
    json_bytes(rows)
    return copy.deepcopy(binding), copy.deepcopy(rows)


def _spec(parameters, torch):
    if not isinstance(parameters, dict):
        raise ValueError("Named tensor parameters are required")
    result = {}
    for name, value in parameters.items():
        if not isinstance(name, str) or not name or not isinstance(value, torch.Tensor) or not value.is_floating_point():
            raise ValueError("Gradient parameters must be named floating point tensors")
        result[name] = {"shape": list(value.shape), "dtype": str(value.dtype)}
    return result


def _validate_gradients(gradients, specification, torch):
    if not isinstance(gradients, dict) or set(gradients) - set(specification):
        raise ValueError("Gradient keys do not match the bound parameter names")
    for name, value in gradients.items():
        if (not isinstance(value, torch.Tensor) or value.layout != torch.strided
                or not value.is_floating_point() or list(value.shape) != specification[name]["shape"]
                or str(value.dtype) != specification[name]["dtype"]):
            raise ValueError("Gradient shape or dtype differs from the bound parameter: " + name)
        if not bool(torch.isfinite(value).all()):
            raise ValueError("Nonfinite gradient: " + name)


def assign_gradients(parameters, gradients, *, torch):
    """Validate completely, then replace every .grad, including absent/None rows.

    No cast, clipping, optimizer mutation or RNG use is performed. Clearing an
    absent parameter is essential when the same resident owner serves candidates.
    """
    _validate_gradients(gradients, _spec(parameters, torch), torch)
    staged = {name: value.detach().to(device=parameters[name].device).clone()
              for name, value in gradients.items()}
    for name, parameter in parameters.items():
        parameter.grad = staged.get(name)


class GradientBankWriter:
    """Single-use writer; incomplete banks have no published manifest.

    ``gradients`` passed to append_actor must be that decision's isolated leaf
    contributions, obtained with every actor .grad=None before its backward (or
    direct hooks). Subtracting two accumulated gradients loses precision.
    Empty dictionaries explicitly represent rows with no actor contribution.
    """

    def __init__(self, path, *, torch, binding, rows, actor_parameters):
        self.binding, self.rows = _bindings(binding, rows)
        self.torch = torch
        self.actor_spec = _spec(actor_parameters, torch)
        if not self.actor_spec:
            raise ValueError("At least one actor parameter must be bound")
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=False)
        self.records = []
        self.closed = False

    def _write(self, name, gradients, specification):
        _validate_gradients(gradients, specification, self.torch)
        payload = {key: value.detach().cpu().contiguous().clone() for key, value in gradients.items()}
        buffer = io.BytesIO()
        self.torch.save(payload, buffer)
        data = buffer.getvalue()
        atomic_write(self.path / name, data)
        return {"file": name, "sha256": digest(data), "bytes": len(data), "parameters": list(payload)}

    def append_actor(self, index, gradients):
        if self.closed or type(index) is not int or index != len(self.records) or index >= len(self.rows):
            raise ValueError("Append every original decision exactly once in its frozen order")
        record = self._write(f"actor-{index:06d}.pt", gradients, self.actor_spec)
        record.update(index=index, row_sha256=digest(json_bytes(self.rows[index])))
        self.records.append(record)
        return copy.deepcopy(record)

    def finalize(self, critic_gradients, *, metadata=None):
        if self.closed or len(self.records) != len(self.rows):
            raise ValueError("Seal only one complete bank containing every admitted decision")
        metadata = {} if metadata is None else copy.deepcopy(metadata)
        json_bytes(metadata)
        critic_spec = _spec(critic_gradients, self.torch)
        critic = self._write("critic.pt", critic_gradients, critic_spec)
        manifest = {"version": VERSION, "binding": self.binding, "rows": self.rows,
                    "actor_parameters": self.actor_spec, "actor": self.records,
                    "critic_parameters": critic_spec, "critic": critic,
                    "metadata": metadata, "scope": SCOPE, "optimizer_steps": 0}
        manifest["manifest_sha256"] = digest(json_bytes(manifest))
        atomic_write(self.path / "manifest.json", json_bytes(manifest))
        self.closed = True
        return copy.deepcopy(manifest)


class GradientBank:
    """A verified manifest whose tensor payloads are checked whenever consumed."""

    def __init__(self, path, *, torch, expected_binding, expected_rows, expected_manifest_sha256=None):
        binding, rows = _bindings(expected_binding, expected_rows)
        self.path, self.torch = Path(path), torch
        manifest = read_json(self.path / "manifest.json")
        seal = manifest.get("manifest_sha256")
        if (manifest.get("version") != VERSION or manifest.get("scope") != SCOPE
                or manifest.get("optimizer_steps") != 0
                or seal != digest(json_bytes({key: value for key, value in manifest.items() if key != "manifest_sha256"}))
                or expected_manifest_sha256 is not None and seal != expected_manifest_sha256):
            raise ValueError("Gradient-bank manifest seal or execution version changed")
        if manifest.get("binding") != binding or manifest.get("rows") != rows:
            raise ValueError("Gradient bank differs from the expected full common or ordered original rows")
        records = manifest.get("actor")
        if not isinstance(records, list) or len(records) != len(rows):
            raise ValueError("Gradient bank omits original admitted decisions")
        for index, record in enumerate(records):
            if (record.get("index") != index or record.get("file") != f"actor-{index:06d}.pt"
                    or record.get("row_sha256") != digest(json_bytes(rows[index]))):
                raise ValueError("Gradient bank row identity or order changed")
        if manifest.get("critic", {}).get("file") != "critic.pt":
            raise ValueError("Gradient bank critic reference changed")
        self.manifest = copy.deepcopy(manifest)

    def _read(self, record, specification, *, device):
        path = self.path / record["file"]
        if path.is_symlink() or path.stat().st_size != record["bytes"] or _sha_file(path) != record["sha256"]:
            raise ValueError("Gradient tensor payload integrity failure: " + record["file"])
        value = self.torch.load(path, map_location="cpu", weights_only=True)
        _validate_gradients(value, specification, self.torch)
        if list(value) != record["parameters"]:
            raise ValueError("Gradient tensor parameter inventory changed")
        return {name: gradient.to(device=device) for name, gradient in value.items()}

    def compose_actor(self, weights, *, device="cpu"):
        """Multiply in stored dtype and accumulate in original decision order.

        A unit weight skips multiplication, preserving the baseline reduction
        path. Residual and other-member weights are supplied as one by the caller;
        no normalization or grouping changes the original actor denominator.
        """
        if (not isinstance(weights, (list, tuple)) or len(weights) != len(self.manifest["actor"])
                or any(type(weight) not in (int, float) or not math.isfinite(weight) or weight <= 0 for weight in weights)):
            raise ValueError("Exactly one finite positive composition weight per original decision is required")
        result = {}
        for record, weight in zip(self.manifest["actor"], weights):
            gradients = self._read(record, self.manifest["actor_parameters"], device=device)
            for name, gradient in gradients.items():
                if weight != 1:
                    gradient = gradient * weight
                if name in result:
                    result[name].add_(gradient)
                else:
                    result[name] = gradient.clone()
        _validate_gradients(result, self.manifest["actor_parameters"], self.torch)
        return result

    def critic_gradients(self, *, device="cpu"):
        """Original unweighted critic accumulation, independent of composition."""
        return self._read(self.manifest["critic"], self.manifest["critic_parameters"], device=device)

    def assign(self, owner, weights):
        """Assign composed gradients; caller restores common first, clips/steps last."""
        actor = self.compose_actor(weights, device=owner.device)
        critic = self.critic_gradients(device=owner.device)
        actor_parameters = owner.actor_parameters
        critic_parameters = dict(owner.critic.named_parameters())
        if (_spec(actor_parameters, self.torch) != self.manifest["actor_parameters"]
                or _spec(critic_parameters, self.torch) != self.manifest["critic_parameters"]):
            raise ValueError("Resident actor/critic parameter schema differs from the bank")
        assign_gradients(actor_parameters, actor, torch=self.torch)
        assign_gradients(critic_parameters, critic, torch=self.torch)
        return {"actor": actor, "critic": critic}


def load_gradient_bank(path, *, torch, expected_binding, expected_rows, expected_manifest_sha256=None):
    return GradientBank(path, torch=torch, expected_binding=expected_binding,
                        expected_rows=expected_rows, expected_manifest_sha256=expected_manifest_sha256)


class WeightedGradientCache:
    """Memoize gradients from the ORIGINAL already-weighted loss backward.

    Unlike the optional unit-gradient bank above, hits are never scaled. Each
    key binds the exact scalar's float.hex(), full numerical/common binding and
    complete ordered-row summary. The updater must perform misses with its
    original ``(base_loss * weight).backward()`` path (including its unit-weight
    branch), restore identical common state, and accumulate in original order.

    This preserves the original arithmetic graph per cached contribution. It
    cannot make nondeterministic GPU kernels bitwise deterministic; a repeated
    GPU backward itself can vary. It does not certify caller provenance or use
    a tolerance to admit a different weight. Critic accumulation is independent.
    """

    def __init__(self, path, *, torch, binding, rows, actor_parameters):
        binding, rows = _bindings(binding, rows)
        specification = _spec(actor_parameters, torch)
        if not specification:
            raise ValueError("At least one actor parameter must be bound")
        self.path, self.torch = Path(path), torch
        header = {"version": WEIGHTED_VERSION, "binding": binding, "rows": rows,
                  "actor_parameters": specification,
                  "weight_encoding": "float.hex; no quantization or approximate matches",
                  "gradient_kind": "leaf contribution of original already-weighted actor loss"}
        header["cache_sha256"] = digest(json_bytes(header))
        if self.path.exists():
            if self.path.is_symlink() or read_json(self.path / "cache.json") != header:
                raise ValueError("Weighted cache differs from the exact common, rows or parameter schema")
        else:
            self.path.mkdir(parents=True, exist_ok=False)
            atomic_write(self.path / "cache.json", json_bytes(header))
        self.header = copy.deepcopy(header)

    def _key(self, index, weight):
        if type(index) is not int or not 0 <= index < len(self.header["rows"]):
            raise ValueError("Weighted cache index is outside the frozen original row inventory")
        if type(weight) not in (int, float) or not math.isfinite(weight) or weight <= 0:
            raise ValueError("An exact finite positive actor weight is required")
        key = {"cache_sha256": self.header["cache_sha256"], "index": index,
               "row_sha256": digest(json_bytes(self.header["rows"][index])),
               "weight_hex": float(weight).hex()}
        return key, digest(json_bytes(key))

    def put(self, index, weight, gradients, *, metadata=None):
        """Publish once; an existing or partially written key is never replaced."""
        key, identifier = self._key(index, weight)
        _validate_gradients(gradients, self.header["actor_parameters"], self.torch)
        metadata = {} if metadata is None else copy.deepcopy(metadata)
        if not isinstance(metadata, dict):
            raise ValueError("Weighted-gradient metadata must be a JSON object")
        json_bytes(metadata)
        payload = {name: value.detach().cpu().contiguous().clone() for name, value in gradients.items()}
        buffer = io.BytesIO()
        self.torch.save(payload, buffer)
        data = buffer.getvalue()
        receipt = {"version": WEIGHTED_VERSION, "key": key, "key_sha256": identifier,
                   "tensor": {"file": "actor.pt", "sha256": digest(data), "bytes": len(data),
                              "parameters": list(payload)}, "metadata": metadata}
        receipt["receipt_sha256"] = digest(json_bytes(receipt))
        directory = self.path / identifier
        # mkdir is the exclusive claim. A crashed or competing writer leaves an
        # explicit incomplete entry, never a payload that another worker overwrites.
        directory.mkdir(exist_ok=False)
        atomic_write(directory / "actor.pt", data)
        atomic_write(directory / "receipt.json", json_bytes(receipt))
        return copy.deepcopy(receipt)

    def get(self, index, weight, *, device="cpu"):
        """Return None only for an absent exact key; corruption is always an error."""
        key, identifier = self._key(index, weight)
        directory = self.path / identifier
        if not directory.exists():
            return None
        if directory.is_symlink() or not (directory / "receipt.json").is_file():
            raise ValueError("Weighted gradient entry is incomplete or an external link")
        receipt = read_json(directory / "receipt.json")
        if (receipt.get("version") != WEIGHTED_VERSION or receipt.get("key") != key
                or receipt.get("key_sha256") != identifier
                or receipt.get("receipt_sha256") != digest(json_bytes({name: value for name, value in receipt.items()
                                                                       if name != "receipt_sha256"}))):
            raise ValueError("Weighted gradient receipt seal, row or exact scalar changed")
        record = receipt["tensor"]
        if record.get("file") != "actor.pt":
            raise ValueError("Weighted gradient payload reference changed")
        path = directory / "actor.pt"
        if path.is_symlink() or path.stat().st_size != record["bytes"] or _sha_file(path) != record["sha256"]:
            raise ValueError("Weighted gradient payload integrity failure")
        gradients = self.torch.load(path, map_location="cpu", weights_only=True)
        _validate_gradients(gradients, self.header["actor_parameters"], self.torch)
        if list(gradients) != record["parameters"]:
            raise ValueError("Weighted gradient parameter inventory changed")
        return {"gradients": {name: value.to(device=device) for name, value in gradients.items()},
                "metadata": copy.deepcopy(receipt["metadata"]), "receipt": receipt}

    def compose_actor(self, weights, *, device="cpu"):
        """Replay complete exact-weight entries in original row order, without scaling."""
        if not isinstance(weights, (list, tuple)) or len(weights) != len(self.header["rows"]):
            raise ValueError("Keep exactly one original actor weight per frozen row")
        result = {}
        for index, weight in enumerate(weights):
            entry = self.get(index, weight, device=device)
            if entry is None:
                raise ValueError("The exact weighted gradient has not been computed for row " + str(index))
            for name, gradient in entry["gradients"].items():
                if name in result:
                    result[name].add_(gradient)
                else:
                    result[name] = gradient.clone()
        _validate_gradients(result, self.header["actor_parameters"], self.torch)
        return result
