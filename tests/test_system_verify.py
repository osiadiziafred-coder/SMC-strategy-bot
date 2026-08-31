from smc_robot.verify import run_verification


def test_required_system_checks_pass(tmp_path):
    report = run_verification(tmp_path)
    failed = [c for c in report["checks"] if not c["ok"]]
    assert report["passed"], failed
