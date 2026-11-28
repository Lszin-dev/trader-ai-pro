"""Encrypted, read-only logical export of TRADER AI PRO application tables.

This is NOT a PostgreSQL transaction snapshot or a complete Supabase backup.
Use a trusted machine, independent private object storage, and a separate
encryption key. Never commit the exports or credentials.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4

from cryptography.fernet import Fernet

TABLE_KEYS = {
    "historico_sinais": ("id",),
    "monitoramento_estado": ("provider", "ativo"),
    "pesquisa_sinais": ("provider", "ativo", "strategy_version", "candle_time", "expiration_minutes"),
}
FORMAT = "trader-ai-pro-logical-export-v1"
PAGE = 500
MAX_ROWS = 100_000
MAX_BYTES = 64 * 1024 * 1024

def _count(client, table):
    result = client.table(table).select("*", count="exact", head=True).execute()
    if result.count is None:
        raise RuntimeError("Contagem indisponível: " + table)
    return int(result.count)

def _export_table(client, table):
    expected = _count(client, table)
    if expected > MAX_ROWS:
        raise RuntimeError("Tabela acima do limite de exportação; use backup PostgreSQL.")
    rows, seen = [], set()
    while len(rows) < expected:
        query = client.table(table).select("*")
        for key in TABLE_KEYS[table]:
            query = query.order(key)
        page = query.range(len(rows), min(len(rows) + PAGE, expected) - 1).execute().data or []
        if not page:
            raise RuntimeError("Leitura incompleta: " + table)
        for row in page:
            key = tuple(row[k] for k in TABLE_KEYS[table])
            if key in seen:
                raise RuntimeError("Chave duplicada durante exportação: " + table)
            seen.add(key)
            rows.append(row)
    if len(rows) != expected or _count(client, table) != expected:
        raise RuntimeError("Quantidade mudou durante exportação: " + table)
    return rows

def collect(client, include_research=True):
    started = datetime.now(timezone.utc).isoformat()
    names = list(TABLE_KEYS) if include_research else list(TABLE_KEYS)[:2]
    tables = {name: _export_table(client, name) for name in names}
    return {
        "format": FORMAT,
        "started_at": started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "consistency": "non_transactional_logical_export",
        "counts": {name: len(rows) for name, rows in tables.items()},
        "tables": tables,
    }

def _validate(payload):
    if payload.get("format") != FORMAT or not isinstance(payload.get("tables"), dict):
        raise ValueError("Formato de backup inválido.")
    tables, counts = payload["tables"], payload["counts"]
    if set(tables) not in (set(TABLE_KEYS), set(list(TABLE_KEYS)[:2])) or set(counts) != set(tables):
        raise ValueError("Tabelas inesperadas ou ausentes.")
    for table, rows in tables.items():
        if not isinstance(rows, list) or counts[table] != len(rows):
            raise ValueError("Contagem inconsistente.")
        keys = [tuple(row[k] for k in TABLE_KEYS[table]) for row in rows]
        if len(set(keys)) != len(keys):
            raise ValueError("Chaves duplicadas.")
    return counts

def seal(payload, key):
    _validate(payload)
    raw = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
    if len(raw) > MAX_BYTES:
        raise ValueError("Backup acima do limite; use backup PostgreSQL.")
    return Fernet(key).encrypt(raw)

def verify(token, key):
    if len(token) > MAX_BYTES * 2:
        raise ValueError("Arquivo acima do limite.")
    payload = json.loads(Fernet(key).decrypt(token))
    return {"format": payload["format"], "counts": _validate(payload), "completed_at": payload["completed_at"]}

def write_encrypted(token, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    name = "trader-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex + ".fernet"
    target = directory / name
    fd, tmp = tempfile.mkstemp(prefix=".backup-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(token)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return target

def upload_verified(client, bucket, object_key, token):
    """Upload ciphertext only; read back and compare exact bytes by hash."""
    digest = hashlib.sha256(token).hexdigest()
    client.put_object(Bucket=bucket, Key=object_key, Body=token,
                      ContentType="application/octet-stream", Metadata={"sha256":digest})
    body = client.get_object(Bucket=bucket, Key=object_key)["Body"]
    try:
        remote = hashlib.sha256()
        size = 0
        for part in body.iter_chunks(chunk_size=1024*1024):
            size += len(part)
            if size > len(token):
                raise RuntimeError("Tamanho remoto inesperado.")
            remote.update(part)
        if size != len(token) or remote.hexdigest() != digest:
            raise RuntimeError("Verificação remota falhou.")
    finally:
        body.close()
    return digest

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--directory", default="private_data/backups")
    create.add_argument("--without-research", action="store_true", help="Somente antes da migração pesquisa_sinais.")
    create.add_argument("--cloud", action="store_true", help="Enviar cópia cifrada ao bucket privado configurado.")
    check = sub.add_parser("verify")
    check.add_argument("file")
    args = parser.parse_args()
    key = os.environ.get("BACKUP_ENCRYPTION_KEY")
    if not key:
        parser.error("Configure BACKUP_ENCRYPTION_KEY somente como segredo do ambiente.")
    try:
        Fernet(key.encode())
        if args.command == "verify":
            print(json.dumps(verify(Path(args.file).read_bytes(), key.encode()), ensure_ascii=False))
            return
        bucket = os.getenv("BACKUP_S3_BUCKET")
        if args.cloud and not bucket:
            parser.error("Configure BACKUP_S3_BUCKET para usar --cloud.")
        from historico import obter_cliente
        payload = collect(obter_cliente(), not args.without_research)
        token = seal(payload, key.encode())
        target = write_encrypted(token, args.directory)
        report = verify(target.read_bytes(), key.encode())
        report["file"] = str(target)
        if args.cloud:
            import boto3
            client = boto3.client("s3", endpoint_url=os.getenv("BACKUP_S3_ENDPOINT") or None)
            object_key = "trader-ai-pro/" + target.name
            report["cloud_sha256"] = upload_verified(client, bucket, object_key, token)
            report["cloud_object"] = object_key
        print(json.dumps(report, ensure_ascii=False))
    except Exception as exc:
        # Avoid printing provider responses, URLs or credentials.
        parser.exit(1, "Backup falhou (" + type(exc).__name__ + "). Verifique configuração, permissões e logs privados.\n")

if __name__ == "__main__":
    main()
