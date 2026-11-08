"""Environment parsing for the backend configuration."""

from __future__ import annotations

from pathlib import Path

from backend.settings import load_backend_config


def test_post_refresh_command_is_parsed_from_the_environment(tmp_path):
    config = load_backend_config(
        {
            "AICOR_DATA_DIR": str(tmp_path),
            "AICOR_POST_REFRESH_COMMAND": "git pull --ff-only",
        }
    )

    assert config.post_refresh_command == ("git", "pull", "--ff-only")
    assert config.public_dict()["post_refresh_configured"] is True


def test_post_refresh_command_defaults_to_none(tmp_path):
    config = load_backend_config({"AICOR_DATA_DIR": str(tmp_path)})

    assert config.post_refresh_command is None
    assert config.public_dict()["post_refresh_configured"] is False


def test_blank_post_refresh_command_is_ignored(tmp_path):
    config = load_backend_config(
        {
            "AICOR_DATA_DIR": str(tmp_path),
            "AICOR_POST_REFRESH_COMMAND": "   ",
        }
    )

    assert config.post_refresh_command is None


def test_pipeline_command_is_parsed_independently(tmp_path):
    config = load_backend_config(
        {
            "AICOR_DATA_DIR": str(tmp_path),
            "AICOR_PIPELINE_COMMAND": "python -m pipeline.run --mode full",
            "AICOR_POST_REFRESH_COMMAND": "git pull",
        }
    )

    assert config.pipeline_command == ("python", "-m", "pipeline.run", "--mode", "full")
    assert config.post_refresh_command == ("git", "pull")


def test_public_dict_never_includes_secrets(tmp_path):
    config = load_backend_config(
        {
            "AICOR_DATA_DIR": str(tmp_path),
            "CRON_SECRET": "cron-secret-value",
            "GITHUB_TOKEN_DISPATCH": "ghs_secret_value",
            "AICOR_GITHUB_REPOSITORY": "owner/aicor",
        }
    )

    public = config.public_dict()

    assert public["refresh_mode"] == "github"
    assert public["refresh_endpoint_enabled"] is True
    assert "cron-secret-value" not in repr(public)
    assert "ghs_secret_value" not in repr(public)
    assert Path(public["data_dir"]) == tmp_path
