"""Read-only inventory. Output contains operational metadata and must stay private."""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def secret_scan(config):
    secrets = {k: v for k, v in config.items() if v and len(v) >= 8
               and any(word in k for word in ("KEY", "SECRET", "PASSWORD"))}
    findings = []
    revisions = subprocess.check_output(["git", "rev-list", "--all"], cwd=ROOT, text=True).split()
    scanned = set()
    for rev in revisions:
        entries = subprocess.check_output(["git", "ls-tree", "-rz", rev], cwd=ROOT).split(b"\0")
        for entry in filter(None, entries):
            metadata, raw_name = entry.split(b"\t", 1)
            blob = metadata.split()[-1].decode()
            if blob in scanned:
                continue
            scanned.add(blob)
            name = raw_name.decode("utf-8")
            data = subprocess.check_output(["git", "cat-file", "blob", blob], cwd=ROOT)
            matched = [key for key, value in secrets.items() if value.encode() in data]
            if matched or re.search(
                rb"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----|sk-[A-Za-z0-9_-]{24,}", data
            ):
                findings.append({"revision": rev[:12], "path": name, "keys": matched})
    return {"revisions": len(revisions), "findings": findings}


def database(config):
    import pymysql

    conn = pymysql.connect(host=config["MYSQL_HOST"], port=int(config.get("MYSQL_PORT", 3306)),
                           user=config["MYSQL_USER"], password=config["MYSQL_PASSWORD"],
                           connect_timeout=8, read_timeout=10)
    try:
        with conn.cursor() as cur:
            cur.execute("SET SESSION TRANSACTION READ ONLY")
            cur.execute("START TRANSACTION READ ONLY")
            cur.execute("SELECT VERSION()")
            version = cur.fetchone()[0]
            cur.execute("SELECT SCHEMA_NAME FROM information_schema.SCHEMATA")
            schemas = [row[0] for row in cur.fetchall()]
            cur.execute("SELECT table_name, table_rows FROM information_schema.tables WHERE table_schema=%s", (config["MYSQL_DATABASE"],))
            tables = [{"table": row[0], "estimated_rows": row[1]} for row in cur.fetchall()]
            return {"version": version, "tables": tables, "read_only": True,
                    "auto_init_configured": config.get("MYSQL_AUTO_INIT"),
                    "configured_schema_exists": config["MYSQL_DATABASE"] in schemas,
                    "visible_schemas": schemas}
    finally:
        conn.rollback()
        conn.close()


def server(access_path, hosts_path):
    import paramiko

    access = json.loads(Path(access_path).read_text(encoding="utf-8"))
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.load_host_keys(str(hosts_path))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(access["host"], port=int(access.get("port", 22)), username=access["username"],
                   password=access["password"], look_for_keys=False, allow_agent=False,
                   timeout=12, banner_timeout=15, auth_timeout=15)
    commands = {
        "system": "cat /etc/os-release; nproc; free -m; df -h /; uptime",
        "containers": "docker ps --format '{{.Names}} | {{.Image}} | {{.Ports}} | {{.Status}}'",
        "resources": "docker stats --no-stream --format '{{.Name}} | {{.MemUsage}} | {{.CPUPerc}}'",
        "networks": "docker network ls",
        "ports": "ss -ltn",
        "sites": "ls -ld /srv/* /opt/* 2>/dev/null",
        "gateway_mounts": "docker ps --filter ancestor=nginx --format '{{.Names}}'",
        "nginx": "docker exec slide-report-studio-nginx-1 nginx -T 2>&1",
        "mounts": "docker inspect slide-report-studio-nginx-1 --format '{{json .Mounts}}'",
        "certificate": "openssl x509 -in /srv/slide-report-studio/ssl/lux-umbra.xyz.pem -noout -dates -issuer -ext subjectAltName",
    }
    result = {}
    try:
        for label, command in commands.items():
            _, out, err = client.exec_command(command, timeout=20)
            result[label] = out.read().decode(errors="replace") + err.read().decode(errors="replace")
        result["host_key_sha256"] = hashlib.sha256(client.get_transport().get_remote_server_key().asbytes()).hexdigest()
    finally:
        client.close()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["history", "database", "server"])
    parser.add_argument("--env", default=str(ROOT / "backend/.env"))
    parser.add_argument("--access")
    parser.add_argument("--known-hosts")
    args = parser.parse_args()
    config = dotenv_values(args.env)
    try:
        result = {"history": lambda: secret_scan(config), "database": lambda: database(config),
                  "server": lambda: server(args.access, args.known_hosts)}[args.mode]()
    except Exception as exc:
        code = exc.args[0] if exc.args and isinstance(exc.args[0], int) else None
        print(json.dumps({"status": "failed", "type": type(exc).__name__, "code": code}))
        raise SystemExit(1) from None
    folder = ROOT / ".local/audit"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{args.mode}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
