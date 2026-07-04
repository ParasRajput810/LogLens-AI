from typer.testing import CliRunner
from loglens.cli import app

runner = CliRunner()

def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "LogLens" in result.output

def test_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output

def test_hello():
    result = runner.invoke(app, ["hello"])
    assert result.exit_code == 0
    assert "alive" in result.output