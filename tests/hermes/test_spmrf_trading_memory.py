from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_trading_review_worker_uses_independent_chatgpt_oauth_and_read_only_codex():
    worker = read("deploy/van-trading-core/spmrf/van-spmrf-review-worker.mjs")
    installer = read("deploy/van-trading-core/spmrf/install-spmrf-review-worker.sh")

    assert "Logged in using ChatGPT" in worker
    assert "permissions: ':read-only'" in worker
    assert "approvalPolicy: 'never'" in worker
    assert "allowProviderModelFallback: false" in worker
    assert "chatgpt-secondary" in worker
    assert 'PIN_VERSION="0.153.1"' in installer
    assert "PIN_INTEGRITY=" in installer
    assert "unset OPENAI_API_KEY CODEX_API_KEY" in installer


def test_review_worker_reuses_cached_repo_mirrors_and_targets_exact_sha():
    worker = read("deploy/van-trading-core/spmrf/van-spmrf-review-worker.mjs")

    assert "mirrors" in worker
    assert "--filter=blob:none" in worker
    assert "worktree" in worker
    assert "repository_sha" in worker
    assert "rev-parse" in worker
    assert "Use the supplied repository-understanding delta to avoid rediscovering the entire project" in worker


def test_shared_memory_clients_are_forced_ssh_stdio_not_public_ports():
    client = read("deploy/van-trading-core/spmrf/install-shared-memory-client.sh")

    assert "StrictHostKeyChecking=yes" in client
    assert "BatchMode=yes" in client
    assert "IdentitiesOnly=yes" in client
    assert "van-spmrf-chatgpt" in client
    assert "van-spmrf-claude" in client
    assert "dial-shared-project-memory" in client
    assert "curl " not in client
    assert "http://" not in client
    assert "https://" not in client


def test_bootstrap_and_qualification_include_spmrf():
    bootstrap = read("deploy/van-trading-core/bootstrap.sh")
    qualifier = read("deploy/van-trading-core/qualify.sh")

    assert "install-spmrf-review-worker.sh" in bootstrap
    assert "install-shared-memory-client.sh" in bootstrap
    assert "spmrf_review_worker" in qualifier
    assert "spmrf_chatgpt_auth" in qualifier
    assert "spmrf_memory_clients" in qualifier
    assert "spmrf_hermes_host_key" in qualifier


def test_review_worker_repo_allowlist_is_bounded():
    worker = read("deploy/van-trading-core/spmrf/van-spmrf-review-worker.mjs")

    assert "https://github.com/Vanguduza/dial-new.git" in worker
    assert "https://github.com/Vanguduza/Van.git" in worker
    assert "repository not allowed for Trading review" in worker
