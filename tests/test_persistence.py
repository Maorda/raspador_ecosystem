from core.cqrs import CommandDispatcher, RegisterExpedienteCommand


def test_cqrs_expediente_registration(db_manager):
    dispatcher = CommandDispatcher(db_manager)
    cmd = RegisterExpedienteCommand(
        numero_expediente="EXP-2026-TEST",
        organo_jurisdiccional="JUZGADO TEST",
        remate_info={"monto": 1000},
        status="COMPLETED",
    )
    result = dispatcher.execute_register_expediente(cmd)
    assert result.is_success and result.value is True
    with db_manager.get_connection() as conn:
        row = conn.execute("SELECT * FROM expedientes WHERE numero_expediente=?", ("EXP-2026-TEST",)).fetchone()
    assert row is not None
    assert row["remate_info"] == '{"monto": 1000}'


def test_task_enqueue_fetch_and_idempotency(blackboard):
    first = blackboard.enqueue_task("REMAJU", "STORAGE", {"action": "SAVE_PDF"}, idempotency_key="EXP-1:PDF")
    second = blackboard.enqueue_task("REMAJU", "STORAGE", {"action": "SAVE_PDF"}, idempotency_key="EXP-1:PDF")
    assert first.is_success and second.is_success
    assert first.value == second.value
    fetched = blackboard.fetch_pending_task("STORAGE")
    assert fetched.is_success
    assert fetched.value["source_plugin"] == "REMAJU"
    assert fetched.value["payload"] == {"action": "SAVE_PDF"}
