import pytest

from ai_shorts import config
from ai_shorts.cli import build_parser
from ai_shorts.errors import ConfigError


@pytest.fixture
def channels(tmp_path, monkeypatch):
    for name in ("alpha", "beta"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "config.example.yaml").write_text("", encoding="utf-8")
    (tmp_path / "notes").mkdir()  # config.example.yaml のないフォルダはチャンネルではない
    monkeypatch.setattr(config, "CHANNELS", tmp_path)
    monkeypatch.delenv("AI_SHORTS_ROOT", raising=False)
    monkeypatch.delenv("AI_SHORTS_CHANNEL", raising=False)
    return tmp_path


def test_channel_names(channels):
    assert config.channel_names() == ["alpha", "beta"]


def test_find_root_by_channel(channels):
    assert config.find_root(channel="beta") == (channels / "beta").resolve()


def test_unknown_channel_lists_channels(channels):
    with pytest.raises(ConfigError, match="alpha / beta"):
        config.find_root(channel="gamma")


def test_env_channel(channels, monkeypatch):
    monkeypatch.setenv("AI_SHORTS_CHANNEL", "alpha")
    assert config.find_root(start=channels.parent) == (channels / "alpha").resolve()


def test_cwd_inside_channel(channels):
    sub = channels / "alpha" / "work"
    sub.mkdir()
    assert config.find_root(start=sub) == channels / "alpha"


def test_no_channel_asks_for_one(channels):
    with pytest.raises(ConfigError, match="--channel"):
        config.find_root(start=channels.parent)


def test_script_root(channels):
    assert config.script_root(["20261120-001", "--channel", "alpha"]) == (channels / "alpha").resolve()
    with pytest.raises(SystemExit):
        config.script_root(["-c", "gamma"])


@pytest.mark.parametrize("argv", [["-c", "alpha", "status"], ["status", "--channel", "alpha"]])
def test_cli_channel_before_or_after(argv):
    assert build_parser().parse_args(argv).channel == "alpha"


def test_cli_without_channel():
    assert build_parser().parse_args(["status"]).channel is None
