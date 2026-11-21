from __future__ import annotations

from customizer.source_secret_scan import SourceSecretScanner


def test_detects_high_confidence_credentials_without_returning_values():
    scanner = SourceSecretScanner()
    scanner.feed(b"config = 'AKIAABCDEFGHIJKLMNOP'")
    assert scanner.findings == {"aws_access_key_id"}


def test_detects_private_key_header():
    scanner = SourceSecretScanner()
    scanner.feed(b"-----BEGIN OPENSSH PRIVATE KEY-----")
    assert scanner.findings == {"private_key_pem"}


def test_detects_tokens_split_across_chunks():
    scanner = SourceSecretScanner()
    scanner.feed(b"prefix ghp_AbCdEfGhIjKlMnOp")
    scanner.feed(b"QrStUvWxYz0123456789abcdef suffix")
    assert scanner.findings == {"github_token"}


def test_scanner_does_not_match_placeholder_or_common_example_values():
    scanner = SourceSecretScanner()
    scanner.feed(b"API_KEY=your-api-key-here\nTOKEN=example-token\n")
    assert scanner.findings == set()


def test_scanner_reports_only_rule_ids_not_secret_values():
    value = b"ghp_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789abcdef"
    scanner = SourceSecretScanner()
    scanner.feed(value)
    assert scanner.findings == {"github_token"}
    assert value.decode() not in repr(scanner.findings)
