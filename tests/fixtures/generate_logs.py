import random
import json
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)

CLUSTERS = {
    "db_connection": [
        "Database connection timeout after {n}s on port {port}",
        "db conn refused at host {host}:{port}",
        "connection to database lost after {n} retries",
        "DB connection pool exhausted max={n} connections",
        "database unreachable host={host} error=ECONNREFUSED",
        "cxn timeout to postgres on {host}:{port}",
        "cnx refused by mysql server {host}",
        "DBConnectionError: could not connect to {host}:{port}",
    ],
    "auth_failure": [
        "Authentication failed for user={user} reason=invalid_password",
        "auth error: token expired for uid={uid}",
        "login failed user={user} ip={ip} attempts={n}",
        "JWT validation failed: signature mismatch uid={uid}",
        "session expired for user={user} after {n}s",
        "AuthService: credential check failed user={user}",
        "invalid credentials provided for {user}",
        "access denied user={user} role=unauthorized",
    ],
    "http_500": [
        "GET /api/users 500 Internal Server Error latency={n}ms",
        "POST /api/orders 500 upstream service unavailable",
        "HTTP 500 on /api/payments handler crashed",
        "500 error: unhandled exception in /api/products",
        "request failed 500 /api/search took {n}ms",
        "gateway error 500 upstream=/api/inventory",
        "InternalServerError: null pointer in /api/cart handler",
        "500 Internal Server Error X-Request-Id={uid}",
    ],
    "memory_oom": [
        "OOM killer activated process={svc} using {n} MB",
        "heap memory exceeded {n} MB threshold",
        "OutOfMemoryError: GC overhead limit exceeded",
        "memory usage critical {n}% of {total} GB",
        "process {svc} killed due to memory limit {n} MB",
        "JVM heap space exhausted Xmx={n}m",
        "container {svc} OOM killed memory={n}Mi",
        "memory leak detected in {svc} grew {n} MB in {t}s",
    ],
    "disk_io": [
        "disk usage {n}% on volume /dev/sda1",
        "I/O error writing to /var/log/{svc}.log",
        "disk write latency {n}ms on /dev/nvme0",
        "storage volume /data almost full {n}% used",
        "file descriptor limit reached fd={n}",
        "slow disk read {n}ms for block device /dev/sdb",
        "ENOSPC: no space left on device /var/data",
        "inode exhaustion on /dev/sda2 {n}% used",
    ],
    "network_latency": [
        "high network latency {n}ms to {host}",
        "packet loss {n}% on interface eth0",
        "TCP retransmit rate {n}% to {host}:{port}",
        "DNS resolution slow {n}ms for {host}",
        "network timeout connecting to {host}:{port}",
        "RTT spike {n}ms on subnet 10.0.{n2}.0",
        "connection pool wait time {n}ms exceeded threshold",
        "load balancer health check failed for {host}:{port}",
    ],
}

NORMAL_LOGS = [
    "User login successful uid={uid}",
    "Request completed GET /api/health 200 {n}ms",
    "Cache hit for key=user:{uid} ttl={n}s",
    "Scheduled job {svc}_cleanup completed in {n}ms",
    "Config reloaded successfully version={n}",
    "Metrics exported to prometheus took {n}ms",
    "Health check passed all {n} services up",
    "Background worker {svc} processed {n} items",
    "Session created for uid={uid} expires_in={n}s",
    "Rate limit check passed for ip={ip} quota={n}",
]

ANOMALIES = [
    "CRITICAL kernel panic null pointer dereference at 0xffffffff",
    "FATAL segfault in core module pid=1 signal=11",
    "EMERGENCY datacenter power failure UPS activated",
    "CRITICAL SSL certificate expired for domain api.internal",
    "FATAL database master node unreachable split-brain detected",
    "CRITICAL cryptographic key rotation failed vault unreachable",
    "EMERGENCY all replica nodes failed cascading failure detected",
    "FATAL corrupted transaction log recovery required",
    "CRITICAL firewall rules flushed accidental purge detected",
    "FATAL primary DNS server unresponsive fallback exhausted",
]

SERVICES   = ["auth-service", "db-service", "api-gateway", "payment-service", "user-service", "cache-service"]
HOSTS      = ["10.0.1.10", "10.0.1.11", "db-primary", "db-replica", "cache-01"]
USERS      = ["alice", "bob", "carol", "dave", "eve", "frank"]
LEVELS_FOR = {
    "db_connection": "ERROR",
    "auth_failure":  "ERROR",
    "http_500":      "ERROR",
    "memory_oom":    "CRITICAL",
    "disk_io":       "WARN",
    "network_latency": "WARN",
}


def fill(template: str) -> str:
    return template.format(
        n=random.randint(1, 9999),
        n2=random.randint(0, 255),
        t=random.randint(1, 300),
        total=random.choice([8, 16, 32, 64]),
        port=random.choice([5432, 3306, 6379, 9200, 8080]),
        host=random.choice(HOSTS),
        svc=random.choice(SERVICES),
        user=random.choice(USERS),
        uid=random.randint(1000, 9999),
        ip=f"192.168.{random.randint(1,254)}.{random.randint(1,254)}",
    )


def make_timestamp(base: datetime, offset_seconds: int) -> str:
    return (base + timedelta(seconds=offset_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def generate(
    output_path: str = "tests/fixtures/large_sample.log",
    label_path:  str = "tests/fixtures/large_sample_labels.json",
    total_logs:  int = 5000,
    anomaly_count: int = 30,
    cluster_ratio: float = 0.5,   # 50% cluster logs, 50% normal
):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    base_time = datetime(2024, 1, 15, 0, 0, 0)
    lines = []
    labels = []   # ground truth: (line_index, cluster_name)

    cluster_names = list(CLUSTERS.keys())
    cluster_logs_total = int(total_logs * cluster_ratio)
    normal_logs_total  = total_logs - cluster_logs_total - anomaly_count

    for i in range(cluster_logs_total):
        cluster = random.choice(cluster_names)
        template = random.choice(CLUSTERS[cluster])
        msg = fill(template)
        level = LEVELS_FOR.get(cluster, "ERROR")
        svc = random.choice(SERVICES)
        ts = make_timestamp(base_time, i * 2)
        line = f"{ts} {level:<8} {svc:<20} {msg}"
        lines.append((i, line, cluster))

    for i in range(normal_logs_total):
        template = random.choice(NORMAL_LOGS)
        msg = fill(template)
        svc = random.choice(SERVICES)
        ts = make_timestamp(base_time, i * 2)
        line = f"{ts} INFO     {svc:<20} {msg}"
        lines.append((cluster_logs_total + i, line, "normal"))

    for i, anomaly_msg in enumerate(random.sample(ANOMALIES * 3, anomaly_count)):
        svc = random.choice(SERVICES)
        ts = make_timestamp(base_time, (total_logs + i) * 2)
        line = f"{ts} CRITICAL {svc:<20} {anomaly_msg}"
        lines.append((total_logs + i, line, "anomaly"))

    random.shuffle(lines)

    label_map = {}
    with open(output_path, "w") as f:
        for idx, (_, line, cluster) in enumerate(lines):
            f.write(line + "\n")
            label_map[idx] = cluster

    with open(label_path, "w") as f:
        json.dump(label_map, f, indent=2)

    print(f"Generated {len(lines):,} log lines → {output_path}")
    print(f"Labels saved → {label_path}")
    print(f"\nCluster breakdown:")
    from collections import Counter
    counts = Counter(label_map.values())
    for k, v in sorted(counts.items()):
        print(f"  {k:<20} {v:>5} lines")


if __name__ == "__main__":
    generate()