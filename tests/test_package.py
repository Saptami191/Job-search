from job_scout import cli


def test_cli_exposes_main():
    assert callable(cli.main)
