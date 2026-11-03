from datetime import datetime, timedelta, timezone


def test_claim_task_changes_state_and_increments_attempts(blackboard):
    queued = blackboard.enqueue_task("REMAJU", "SUNARP", {"partida": "123"}, idempotency_key="SUNARP:123")
    assert queued.is_success
    claim = blackboard.claim_pending_task("SUNARP", lease_seconds=60)
    assert claim.is_success and claim.value is not None
    assert claim.value["id"] == queued.value
    assert claim.value["status"] == "PROCESSING"
    assert claim.value["attempts"] == 1
    assert claim.value["lease_token"]


def test_only_current_lease_can_complete(blackboard):
    queued = blackboard.enqueue_task("REMAJU", "CEJ", {"expediente": "EXP-1"})
    claim = blackboard.claim_pending_task("CEJ").value
    assert claim["id"] == queued.value
    invalid = blackboard.complete_task(claim["id"], "wrong-token")
    assert invalid.is_success and invalid.value is False
    valid = blackboard.complete_task(claim["id"], claim["lease_token"])
    assert valid.is_success and valid.value is True


def test_failure_requeues_until_attempt_limit(blackboard):
    queued = blackboard.enqueue_task("REMAJU", "SUNARP", {}, max_attempts=2)
    first = blackboard.claim_pending_task("SUNARP").value
    failed = blackboard.fail_task(first["id"], first["lease_token"], "transient", retry_delay_seconds=0)
    assert failed.is_success and failed.value is True
    second = blackboard.claim_pending_task("SUNARP").value
    assert second["attempts"] == 2
    failed_again = blackboard.fail_task(second["id"], second["lease_token"], "again")
    assert failed_again.is_success and failed_again.value is True
    with blackboard.db.get_connection() as conn:
        row = conn.execute("SELECT status FROM task_queue WHERE id=?", (queued.value,)).fetchone()
    assert row["status"] == "FAILED"


def test_expired_lease_is_recovered(blackboard):
    queued = blackboard.enqueue_task("REMAJU", "CEJ", {}, max_attempts=3)
    claim = blackboard.claim_pending_task("CEJ", lease_seconds=1).value
    with blackboard.db.get_connection() as conn:
        conn.execute(
            "UPDATE task_queue SET lease_until=? WHERE id=?",
            ((datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(timespec="seconds"), queued.value),
        )
    recovered = blackboard.recover_expired_tasks()
    assert recovered.is_success and recovered.value == 1
    with blackboard.db.get_connection() as conn:
        row = conn.execute("SELECT status, lease_token FROM task_queue WHERE id=?", (queued.value,)).fetchone()
    assert row["status"] == "PENDING"
    assert row["lease_token"] is None


def test_no_task_claimed_twice_sequentially(blackboard):
    blackboard.enqueue_task("REMAJU", "SUNARP", {"partida": "P-1"})
    first = blackboard.claim_pending_task("SUNARP")
    second = blackboard.claim_pending_task("SUNARP")
    assert first.value is not None
    assert second.value is None


def test_expired_lease_cannot_complete(blackboard):
    queued = blackboard.enqueue_task("REMAJU", "SUNARP", {}, max_attempts=3)
    claim = blackboard.claim_pending_task("SUNARP", lease_seconds=30).value
    with blackboard.db.get_connection() as conn:
        conn.execute(
            "UPDATE task_queue SET lease_until=? WHERE id=?",
            ((datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(timespec="seconds"), queued.value),
        )
    result = blackboard.complete_task(claim["id"], claim["lease_token"])
    assert result.is_success and result.value is False


def test_recovery_marks_exhausted_task_failed(blackboard):
    queued = blackboard.enqueue_task("REMAJU", "CEJ", {}, max_attempts=1)
    blackboard.claim_pending_task("CEJ", lease_seconds=30)
    with blackboard.db.get_connection() as conn:
        conn.execute(
            "UPDATE task_queue SET lease_until=? WHERE id=?",
            ((datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(timespec="seconds"), queued.value),
        )
    recovered = blackboard.recover_expired_tasks()
    assert recovered.is_success and recovered.value == 1
    with blackboard.db.get_connection() as conn:
        row = conn.execute("SELECT status FROM task_queue WHERE id=?", (queued.value,)).fetchone()
    assert row["status"] == "FAILED"


def test_two_workers_cannot_claim_the_same_task(blackboard):
    import threading

    queued = blackboard.enqueue_task("REMAJU", "SUNARP", {"partida": "P-CONCURRENT"})
    barrier = threading.Barrier(2)
    results = []

    def worker():
        barrier.wait()
        results.append(blackboard.claim_pending_task("SUNARP", lease_seconds=30))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert all(not thread.is_alive() for thread in threads)
    assert all(result.is_success for result in results)
    claimed = [result.value for result in results if result.value is not None]
    assert len(claimed) == 1
    assert claimed[0]["id"] == queued.value
