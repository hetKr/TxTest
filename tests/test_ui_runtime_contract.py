import asyncio


def test_ui_orchestrator_contract_smoke(mock_orchestrator) -> None:
    orchestrator = mock_orchestrator

    run = orchestrator.request_run("ST01", "basic_healthcheck", "operator")
    assert run.station_id == "ST01"
    assert hasattr(orchestrator, "active")

    plan = asyncio.run(orchestrator.dry_run("ST01", "basic_healthcheck"))
    assert plan["package_name"] == "basic_healthcheck"
    assert isinstance(plan["plan"], list)
    assert plan["plan"][0]["test_name"] == "preflight_check"

    assert orchestrator.cancel_run(run.run_id, "operator") is True
