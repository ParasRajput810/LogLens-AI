from loglens.pipeline.parser import detect_format, parse_line

def test_detect_standard_format():
    line = "2024-01-15T10:00:00Z INFO [nginx] GET /api 200"
    assert detect_format(line) == "STANDARD"

def test_detect_json_format():
    line = '{"timestamp": "2024-01-15", "level": "ERROR", "message": "timeout"}'
    assert detect_format(line) == "JSON"

def test_detect_nginx_format():
    line = '192.168.1.1 - - [15/Jan/2024:10:00:00 +0000] "GET /api 200" 200 1240'
    assert detect_format(line) == "NGINX"

def test_detect_plaintext_format():
    line = "something went wrong unexpectedly"
    assert detect_format(line) == "PLAINTEXT"

def test_malformed_line_returns_none():
    assert parse_line("", "STANDARD") is None

def test_logentry_dataclass_fields():
    line = "2024-01-15T10:00:00Z ERROR [payment-service] DB timeout"
    entry = parse_line(line, "STANDARD")
    assert entry is not None
    assert entry.level == "ERROR"
    assert entry.service == "payment-service"
    assert entry.message == "DB timeout"

def test_json_parse():
    line = '{"timestamp": "2024-01-15", "level": "error", "service": "auth", "message": "token expired"}'
    entry = parse_line(line, "JSON")
    assert entry is not None
    assert entry.level == "ERROR"
    assert entry.service == "auth"