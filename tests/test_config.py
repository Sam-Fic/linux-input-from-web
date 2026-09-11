"""Unit tests for config load / save / profile validation."""

import json

import pytest

from input_from_web import config
from input_from_web.config import DEFAULT_CONFIG


@pytest.fixture
def conf_path(tmp_path, monkeypatch):
    path = tmp_path / "conf.json"
    monkeypatch.setattr(config, "CONFIG_PATH", str(path))
    return path


def test_creates_default_config_on_missing(conf_path):
    profile, name, full = config.load_or_create_config()
    assert conf_path.exists()
    assert name == "default"
    assert profile["method"] == "type"
    assert profile["paste_key"] == "ctrl+v"
    assert profile["voice_send"]["send_words"] == ["send", "发送"]
    assert full == DEFAULT_CONFIG


def test_reads_existing_config(conf_path):
    conf_path.write_text(
        json.dumps(
            {"default_profile": "alt", "profiles": {"alt": {"method": "clipboard"}}}
        ),
        encoding="utf-8",
    )
    profile, name, full = config.load_or_create_config()
    assert name == "alt"
    assert profile["method"] == "clipboard"
    # file untouched, no default written
    assert conf_path.read_text(encoding="utf-8") != json.dumps(DEFAULT_CONFIG)


def test_unknown_profile_exits(conf_path):
    with pytest.raises(SystemExit):
        config.load_or_create_config(profile_name="nope")


def test_save_config_roundtrip(conf_path):
    conf_path.write_text(json.dumps(DEFAULT_CONFIG), encoding="utf-8")
    _, _, full = config.load_or_create_config()
    full["profiles"]["default"]["method"] = "clipboard"
    config.save_config(full)
    reloaded = json.loads(conf_path.read_text(encoding="utf-8"))
    assert reloaded["profiles"]["default"]["method"] == "clipboard"