"""Count one verified local text-renderer contract; every other contract stays conservative."""
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
import json
import re

import httpx

# Ollama v0.40.3/eab97e9, v0.40.6/2476d5e, v0.40.10/f52b9e7 and v0.40.11/675150d, qwen3.8 variant.
# 0.40.11 keeps this text renderer; its new BPE metaspace mode is excluded below.
# shortcut: other engine versions/history/media need their own renderer verification.
ENGINE_VERSIONS = ('0.40.3', '0.40.6', '0.40.10', '0.40.11')
GO_SPACE = ' \t\n\v\f\r\x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000'
PATTERN = r"(?i:'s|'t|'re|'ve|'m|'ll|'d)|[^\r\n\p{L}\p{N}]?[\p{L}\p{M}]+|\p{N}| ?[^\s\p{L}\p{N}]+[\r\n]*|\s*[\r\n]+|\s+(?!\S)|\s+"


def fingerprint(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def render(messages, think):
    if (think is not False or not isinstance(messages, list) or len(messages) != 2
            or any(not isinstance(m, dict) for m in messages)
            or [m.get('role') for m in messages] != ['system', 'user']
            or any(set(m) != {'role', 'content'} or not isinstance(m['content'], str) for m in messages)):
        raise ValueError('unsupported_message_contract')
    system, user = [m['content'].strip(GO_SPACE) for m in messages]
    if not user or any('<|' in m['content'] or '<tool_response>' in m['content'] for m in messages):
        raise ValueError('unsupported_empty_or_special_input')
    return (('<|im_start|>system\n' + system + '<|im_end|>\n') if system else '') + (
        '<|im_start|>user\n' + user + '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n')


def get(client, endpoint, path, body=None):
    response = client.get(endpoint + path) if body is None else client.post(endpoint + path, json=body)
    response.raise_for_status()
    return response.json()


def model_digest(client, endpoint, model):
    return next((m['digest'] for m in get(client, endpoint, '/api/tags')['models'] if m['name'] == model), None)


def configuration(shown):
    return dict({k: shown.get(k) for k in ('template', 'system', 'messages', 'details', 'requires')},
        parameters=sorted(shown.get('parameters', '').splitlines()),
        rendering=sorted(line for line in shown.get('modelfile', '').splitlines()
            if line.startswith(('FROM ', 'RENDERER ', 'PARSER '))))


@lru_cache(maxsize=16)
def verified_blob(path, size, modified, changed):
    value = sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            value.update(chunk)
    if Path(path).name != 'sha256-' + value.hexdigest():
        raise ValueError('local_blob_digest_mismatch')
    return value.hexdigest()


def blob(path):
    stat = path.stat()
    return verified_blob(str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def local_model(shown, digest):
    paths = [Path(p) for p in re.findall(r'^FROM (/.+)$', shown['modelfile'], re.M)]
    if (not paths or any(p.parent.name != 'blobs' or not re.fullmatch(r'sha256-[0-9a-f]{64}', p.name) for p in paths)
            or len({p.parent for p in paths}) != 1):
        raise ValueError('unverified_local_model_store')
    store = paths[0].parent.parent
    manifests = [p.read_bytes() for p in (store / 'manifests').rglob('*') if p.is_file()]
    manifest = next((json.loads(v) for v in manifests if sha256(v).hexdigest() == digest), None)
    if manifest is None:
        raise ValueError('local_manifest_digest_mismatch')
    allowed = {'model', 'projector', 'license', 'params'}
    if any(l['mediaType'].removeprefix('application/vnd.ollama.image.') not in allowed for l in manifest['layers']):
        raise ValueError('unsupported_model_layers')
    config_path = store / 'blobs' / manifest['config']['digest'].replace(':', '-')
    if 'sha256:' + blob(config_path) != manifest['config']['digest']:
        raise ValueError('local_configuration_digest_mismatch')
    config = json.loads(config_path.read_text())
    if config.get('renderer') != 'qwen3.8' or config.get('model_format') != 'gguf':
        raise ValueError('unsupported_local_renderer')
    files = [l for l in manifest['layers'] if l['mediaType'] in {
        'application/vnd.ollama.image.model', 'application/vnd.ollama.image.projector'}]
    if {p.name for p in paths} != {l['digest'].replace(':', '-') for l in files}:
        raise ValueError('serving_blob_manifest_mismatch')
    for layer in manifest['layers']:
        path = store / 'blobs' / layer['digest'].replace(':', '-')
        if path.stat().st_size != layer['size'] or 'sha256:' + blob(path) != layer['digest']:
            raise ValueError('local_layer_digest_mismatch')
    return dict(local_manifest_digest=digest, local_configuration_digest=manifest['config']['digest'],
                content_addresses_verified=True, renderer=config['renderer'])


@lru_cache(maxsize=2)
def tokenizer(endpoint, model, digest, config_hash, transport):
    from tokenizers import Tokenizer, Regex, AddedToken, models, pre_tokenizers, decoders
    with httpx.Client(timeout=15, trust_env=False, follow_redirects=False, transport=transport) as client:
        shown = get(client, endpoint, '/api/show', {'model': model, 'verbose': True})
        if fingerprint(configuration(shown)) != config_hash or model_digest(client, endpoint, model) != digest:
            raise ValueError('model_changed_during_tokenizer_read')
    meta = shown['model_info']
    if (meta.get('tokenizer.ggml.model') != 'gpt2' or meta.get('tokenizer.ggml.pre') != 'qwen35'
            or meta.get('tokenizer.ggml.add_bos_token') is not False
            or meta.get('tokenizer.ggml.metaspace.prepend_scheme', 'never') != 'never'):
        raise ValueError('unsupported_tokenizer_contract')
    words, kinds, merges = [meta['tokenizer.ggml.' + k] for k in ('tokens', 'token_type', 'merges')]
    vocab = {word: i for i, word in enumerate(words)}
    if not words or len(vocab) != len(words) or len(kinds) != len(words):
        raise ValueError('invalid_tokenizer_metadata')
    counter = Tokenizer(models.BPE(vocab=vocab, merges=[tuple(row.split(' ')) for row in merges],
                                   unk_token=None, byte_fallback=False))
    counter.pre_tokenizer = pre_tokenizers.Sequence([pre_tokenizers.Split(Regex(PATTERN), behavior='isolated'),
        pre_tokenizers.ByteLevel(add_prefix_space=False, use_regex=False)])
    counter.decoder = decoders.ByteLevel()
    counter.add_special_tokens([AddedToken(word, normalized=False, special=True)
        for word, kind in zip(words, kinds) if kind in {3, 4}])
    if counter.get_vocab_size() != len(words):
        raise ValueError('tokenizer_vocabulary_changed')
    return counter, fingerprint({k: v for k, v in meta.items() if k.startswith('tokenizer.')})


def count(config, model, identity, messages, schema, think, *, transport=None):
    """Metadata requests and streamed identity hashing only; no weights/model initialization."""
    try:
        prompt = render(messages, think)
        if config.get('provider') != 'ollama':
            raise ValueError('unsupported_provider')
        from .endpoint import local_ollama_url
        endpoint = local_ollama_url(config.get('endpoint', ''))
        expected = identity.get('digest') if isinstance(identity, dict) else None
        if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
            raise ValueError('unverified_expected_model_digest')
        with httpx.Client(timeout=15, trust_env=False, follow_redirects=False, transport=transport) as client:
            version = get(client, endpoint, '/api/version').get('version')
            if version not in ENGINE_VERSIONS:
                raise ValueError('unsupported_engine_version')
            if model_digest(client, endpoint, model) != expected:
                raise ValueError('serving_identity_changed')
            shown = get(client, endpoint, '/api/show', {'model': model})
            if (shown.get('template') != '{{ .Prompt }}' or shown.get('system') or shown.get('messages')
                    or re.findall(r'^RENDERER (.+)$', shown.get('modelfile', ''), re.M) != ['qwen3.8']):
                raise ValueError('unsupported_serving_template')
            local = local_model(shown, expected)
            config_hash = fingerprint(configuration(shown))
            counter, metadata_hash = tokenizer(endpoint, model, expected, config_hash, transport)
            if model_digest(client, endpoint, model) != expected:
                raise ValueError('serving_identity_changed')
        encoded = counter.encode(prompt, add_special_tokens=False)
        if counter.decode(encoded.ids, skip_special_tokens=False) != prompt:
            raise ValueError('tokenizer_roundtrip_mismatch')
        schema_tokens = len(counter.encode(json.dumps(schema, ensure_ascii=False, separators=(',', ':')),
            add_special_tokens=False).ids) if schema is not None else 0
        return dict(prompt_tokens=len(encoded.ids), prompt_exact=True, prompt_sha256=sha256(prompt.encode()).hexdigest(),
            schema_serialized_tokens=schema_tokens, schema_reserve_tokens=schema_tokens,
            schema_reserve_is_separate_grammar_not_observed_prompt=True, model_digest=expected,
            configuration_sha256=config_hash, tokenizer_metadata_sha256=metadata_hash,
            renderer_contract='ollama-qwen38-text-system-user-think-false-v' + version, **local), None
    except (httpx.HTTPError, OSError, ValueError, TypeError, KeyError, ImportError) as exc:
        return None, str(exc) if isinstance(exc, ValueError) else type(exc).__name__
