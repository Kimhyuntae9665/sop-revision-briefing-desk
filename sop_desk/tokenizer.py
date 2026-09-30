"""CPU reconstruction of the installed Qwen GGUF tokenizer, never model weights.

Input must already be the exact rendered Ollama prompt. This module does not
render templates, infer, download models, or claim runner parity before a separate
runner cross-check.
"""
from __future__ import annotations

import hashlib
import importlib
import struct
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

MODEL_DIGEST = "3e4cb14174460404e7a233e531675303b2fbf7749c02f91864fe311ab6344e4f"
DEFAULT_GGUF_PATH = Path("/usr/share/ollama/.ollama/models/blobs/sha256-" + MODEL_DIGEST)
EXPECTED_METADATA_SHA256 = "82e92c41ef7f47671922432da66dce6a15bb89d54b429f410820f47e91583621"
ENGINE_VERSION = "0.23.2"
MAX_METADATA_BYTES = 32 * 1024 * 1024
MAX_STRING_BYTES = 2 * 1024 * 1024
MAX_ARRAY_ITEMS = 2_000_000
MAX_PROMPT_BYTES = 1024 * 1024
QWEN2_PATTERN = r"(?:'[sS]|'[tT]|'[rR][eE]|'[vV][eE]|'[mM]|'[lL][lL]|'[dD])|[^\r\n\p{L}\p{N}]?\p{L}+|\p{N}| ?[^\s\p{L}\p{N}]+[\r\n]*|\s*[\r\n]+|\s+(?!\S)|\s+"
_NUMERIC = {0: ("B", 1), 1: ("b", 1), 2: ("H", 2), 3: ("h", 2),
            4: ("I", 4), 5: ("i", 4), 6: ("f", 4), 10: ("Q", 8),
            11: ("q", 8), 12: ("d", 8)}


class TokenizerError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class GGUFMetadata:
    values: object
    metadata_sha256: str
    metadata_bytes: int
    version: int
    tensor_count: int


class _Reader:
    def __init__(self, handle):
        self.handle = handle
        self.consumed = 0
        self.hasher = hashlib.sha256()

    def read(self, count):
        if type(count) is not int or count < 0 or self.consumed + count > MAX_METADATA_BYTES:
            raise TokenizerError("metadata_budget", "GGUF metadata exceeds the bounded read budget")
        data = self.handle.read(count)
        if len(data) != count:
            raise TokenizerError("truncated_gguf", "GGUF metadata is truncated")
        self.consumed += count
        self.hasher.update(data)
        return data

    def scalar(self, kind):
        fmt, count = _NUMERIC[kind]
        return struct.unpack("<" + fmt, self.read(count))[0]

    def string(self):
        size = self.scalar(10)
        if size > MAX_STRING_BYTES:
            raise TokenizerError("metadata_string_budget", "GGUF metadata string exceeds the limit")
        try:
            return self.read(size).decode("utf-8")
        except UnicodeError as exc:
            raise TokenizerError("metadata_unicode", "GGUF strings must be valid UTF-8") from exc

    def value(self, kind, depth=0):
        if depth > 4:
            raise TokenizerError("metadata_depth", "GGUF array nesting exceeds the limit")
        if kind in _NUMERIC:
            return self.scalar(kind)
        if kind == 7:
            value = self.scalar(0)
            if value not in (0, 1):
                raise TokenizerError("metadata_bool", "GGUF boolean must be zero or one")
            return bool(value)
        if kind == 8:
            return self.string()
        if kind == 9:
            element_type, length = self.scalar(4), self.scalar(10)
            if element_type not in {*_NUMERIC, 7, 8, 9}:
                raise TokenizerError("metadata_type", "Unsupported GGUF metadata array element type")
            if length > MAX_ARRAY_ITEMS:
                raise TokenizerError("metadata_array_budget", "GGUF metadata array exceeds the limit")
            return tuple(self.value(element_type, depth + 1) for _ in range(length))
        raise TokenizerError("metadata_type", "Unsupported GGUF metadata value type")


def read_gguf_metadata(path=DEFAULT_GGUF_PATH):
    """Read GGUF v3 header and key/value region only; stop before tensor info."""
    try:
        with Path(path).open("rb") as handle:
            reader = _Reader(handle)
            if reader.read(4) != b"GGUF":
                raise TokenizerError("gguf_magic", "Expected GGUF metadata")
            version = reader.scalar(4)
            if version != 3:
                raise TokenizerError("gguf_version", "Only the pinned GGUF v3 format is supported")
            tensor_count, count = reader.scalar(10), reader.scalar(10)
            if tensor_count > 100000 or count > 2048:
                raise TokenizerError("metadata_count", "GGUF header exceeds bounded count limits")
            values = {}
            for _ in range(count):
                key = reader.string()
                if not key or key in values:
                    raise TokenizerError("metadata_duplicate_key", "GGUF metadata keys must be unique")
                values[key] = reader.value(reader.scalar(4))
            return GGUFMetadata(MappingProxyType(values), reader.hasher.hexdigest(),
                                reader.consumed, version, tensor_count)
    except OSError as exc:
        raise TokenizerError("gguf_unavailable", "Configured GGUF metadata is unavailable") from exc


def _check_metadata(metadata, expected_metadata_sha256):
    if metadata.metadata_sha256 != expected_metadata_sha256:
        raise TokenizerError("metadata_hash_mismatch", "GGUF metadata differs from the frozen tokenizer pin")
    values = metadata.values
    requirements = {"tokenizer.ggml.model": "gpt2", "tokenizer.ggml.pre": "qwen2",
                    "tokenizer.ggml.add_bos_token": False,
                    "tokenizer.ggml.bos_token_id": 151643, "tokenizer.ggml.eos_token_id": 151645}
    for key, expected in requirements.items():
        if key not in values or type(values[key]) is not type(expected) or values[key] != expected:
            raise TokenizerError("tokenizer_config_mismatch", "Installed tokenizer configuration differs from Qwen pin")
    if values.get("tokenizer.ggml.add_eos_token", False) is not False:
        raise TokenizerError("unsupported_eos", "Automatic EOS addition is unsupported")
    tokens, merges, types = (values.get("tokenizer.ggml." + name) for name in ("tokens", "merges", "token_type"))
    if not all(isinstance(value, tuple) for value in (tokens, merges, types)):
        raise TokenizerError("tokenizer_arrays_missing", "Vocabulary, merge ranks and token types are required")
    if len(tokens) != 151936 or len(merges) != 151387 or len(types) != len(tokens):
        raise TokenizerError("tokenizer_size_mismatch", "Installed vocabulary sizes differ from Qwen pin")
    if any(not isinstance(token, str) or not token for token in tokens) or len(set(tokens)) != len(tokens):
        raise TokenizerError("invalid_vocabulary", "Vocabulary strings must be nonempty and unique")
    if any(type(kind) is not int or kind not in range(1, 7) for kind in types):
        raise TokenizerError("invalid_token_type", "Unsupported GGUF token type")
    return tokens, merges, types


@dataclass(frozen=True)
class GGUFTokenizer:
    _engine: object
    provenance: object

    def encode(self, rendered_prompt):
        if not isinstance(rendered_prompt, str):
            raise TokenizerError("invalid_prompt", "Rendered prompt must be a string")
        try:
            raw = rendered_prompt.encode("utf-8")
        except UnicodeError as exc:
            raise TokenizerError("invalid_prompt_unicode", "Rendered prompt must contain valid Unicode scalars") from exc
        if len(raw) > MAX_PROMPT_BYTES:
            raise TokenizerError("prompt_byte_budget", "Rendered prompt exceeds the CPU byte bound")
        try:
            # No normalizer, BOS/EOS processor, padding, or truncation exists.
            # Registered special strings still parse with add_special_tokens=False.
            return tuple(self._engine.encode(rendered_prompt, add_special_tokens=False).ids)
        except Exception as exc:
            raise TokenizerError("tokenization_failed", "CPU tokenizer could not tokenize the exact prompt") from exc

    def count(self, rendered_prompt):
        return len(self.encode(rendered_prompt))

    def count_rendered_prompt(self, rendered_prompt):
        ids = self.encode(rendered_prompt)
        raw = rendered_prompt.encode("utf-8")
        return {"input_tokens": len(ids), "rendered_prompt_sha256": hashlib.sha256(raw).hexdigest(),
                "prompt_utf8_bytes": len(raw), "provenance": dict(self.provenance),
                "count_kind": "cpu_reconstructed_bpe", "runner_crosscheck_verified": False}


def load_tokenizer(path=DEFAULT_GGUF_PATH, *, expected_metadata_sha256=EXPECTED_METADATA_SHA256):
    metadata = read_gguf_metadata(path)
    tokens, merges, token_types = _check_metadata(metadata, expected_metadata_sha256)
    try:
        library = importlib.import_module("tokenizers")
        if library.__version__ != ENGINE_VERSION:
            raise TokenizerError("engine_version_mismatch", "CPU tokenizers engine must match the pinned version")
        from tokenizers import Tokenizer, AddedToken, Regex
        from tokenizers.models import BPE
        from tokenizers.pre_tokenizers import Sequence, Split, ByteLevel
        from tokenizers.decoders import ByteLevel as ByteLevelDecoder
    except ImportError as exc:
        raise TokenizerError("tokenizers_unavailable", "Install the pinned official tokenizers CPU wheel") from exc
    pairs = []
    for merge in merges:
        if not isinstance(merge, str) or len(merge.split(" ")) != 2:
            raise TokenizerError("invalid_merge", "Each GGUF BPE merge must contain exactly two byte-encoded tokens")
        left, right = merge.split(" ")
        if not left or not right:
            raise TokenizerError("invalid_merge", "BPE merge operands must be nonempty")
        pairs.append((left, right))
    vocab = {token: index for index, token in enumerate(tokens)}
    try:
        engine = Tokenizer(BPE(vocab=vocab, merges=pairs, dropout=None, unk_token=None,
                               fuse_unk=False, byte_fallback=False))
        engine.pre_tokenizer = Sequence([Split(Regex(QWEN2_PATTERN), behavior="isolated"),
                                          ByteLevel(add_prefix_space=False, use_regex=False)])
        engine.decoder = ByteLevelDecoder()
        specials = [(index, token) for index, (token, kind) in enumerate(zip(tokens, token_types))
                    if kind in (2, 3, 4)]
        engine.add_special_tokens([AddedToken(token, special=True, normalized=False,
                                             lstrip=False, rstrip=False, single_word=False)
                                   for _, token in specials])
        if engine.get_vocab_size() != len(tokens) or any(engine.token_to_id(token) != index
                                                        for index, token in specials):
            raise TokenizerError("special_id_mismatch", "Special token registration changed GGUF token IDs")
        for index, token in specials:
            if tuple(engine.encode(token, add_special_tokens=False).ids) != (index,):
                raise TokenizerError("special_parse_mismatch", "Special-token parsing differs from the GGUF IDs")
        alphabet = ByteLevel.alphabet()
        if len(alphabet) != 256 or any(byte not in vocab for byte in alphabet):
            raise TokenizerError("byte_alphabet_missing", "GPT2 byte-level alphabet is incomplete")
    except TokenizerError:
        raise
    except Exception as exc:
        raise TokenizerError("tokenizer_build_failed", "CPU tokenizer reconstruction failed") from exc
    provenance = {"engine": "huggingface/tokenizers", "engine_version": ENGINE_VERSION,
                  "metadata_sha256": metadata.metadata_sha256, "metadata_bytes_read": metadata.metadata_bytes,
                  "model_manifest_layer_digest": "sha256:" + MODEL_DIGEST,
                  "model_digest_full_file_rehashed": False, "gguf_version": metadata.version,
                  "ggml_model": "gpt2", "ggml_pre": "qwen2", "vocabulary_size": len(tokens),
                  "merge_count": len(merges), "special_tokens": len(specials),
                  "parse_special": True, "add_bos": False, "add_eos": False,
                  "regex_sha256": hashlib.sha256(QWEN2_PATTERN.encode()).hexdigest(),
                  "normalization": None, "truncation": False}
    return GGUFTokenizer(engine, MappingProxyType(provenance))


def count_rendered_prompt(rendered_prompt, *, tokenizer=None, path=DEFAULT_GGUF_PATH):
    return (tokenizer or load_tokenizer(path)).count_rendered_prompt(rendered_prompt)
