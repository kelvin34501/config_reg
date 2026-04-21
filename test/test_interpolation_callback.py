"""Tests for interpolation-related callbacks."""

import argparse

import pytest

from config_reg import ConfigEntrySource, ConfigRegistry
from config_reg.callback import CurrentValueInterpolationCallback, InterpolationCallback


def create_parser(reg: ConfigRegistry) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    reg.hook(parser)
    return parser


class TestInterpolationCallback:
    """Tests for InterpolationCallback."""

    def test_interpolates_single_dependency(self):
        reg = ConfigRegistry()
        reg.register("model.name", category=str, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default="resnet")
        reg.register(
            "output.dir",
            category=str,
            source=ConfigEntrySource.CALLBACK,
            callback=InterpolationCallback("runs/?(model.name)"),
        )

        parser = create_parser(reg)
        reg.parse(parser, [])

        assert reg.config["output"]["dir"] == "runs/resnet"

    def test_interpolates_multiple_dependencies(self):
        reg = ConfigRegistry()
        reg.register("root.dir", category=str, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default="runs")
        reg.register("model.name", category=str, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default="resnet")
        reg.register(
            "output.dir",
            category=str,
            source=ConfigEntrySource.CALLBACK,
            callback=InterpolationCallback("?(root.dir)/?(model.name)/artifacts"),
        )

        parser = create_parser(reg)
        reg.parse(parser, [])

        assert reg.config["output"]["dir"] == "runs/resnet/artifacts"


class TestCurrentValueInterpolationCallback:
    """Tests for CurrentValueInterpolationCallback."""

    def test_uses_default_template_when_current_value_unspecified(self):
        reg = ConfigRegistry()
        reg.register("model.name", category=str, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default="resnet")
        reg.register(
            "output.dir",
            category=str,
            source=ConfigEntrySource.CALLBACK,
            callback=CurrentValueInterpolationCallback("runs/?(model.name)"),
        )

        parser = create_parser(reg)
        reg.parse(parser, [])

        assert reg.config["output"]["dir"] == "runs/resnet"

    def test_uses_current_value_as_template_when_overridden(self):
        reg = ConfigRegistry()
        reg.register("model.name", category=str, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default="resnet")
        reg.register(
            "output.dir",
            category=str,
            source=ConfigEntrySource.CALLBACK,
            callback=CurrentValueInterpolationCallback("runs/?(model.name)"),
        )

        parser = create_parser(reg)
        reg.parse(parser, [], cfg_override={"output": {"dir": "artifacts/?(model.name)"}})

        assert reg.config["output"]["dir"] == "artifacts/resnet"

    def test_raises_for_dependency_used_only_in_current_value(self):
        reg = ConfigRegistry()
        reg.register("model.name", category=str, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default="resnet")
        reg.register("suffix", category=str, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default="ckpt")
        reg.register(
            "output.dir",
            category=str,
            source=ConfigEntrySource.CALLBACK,
            callback=CurrentValueInterpolationCallback("runs/?(model.name)"),
        )

        parser = create_parser(reg)

        with pytest.raises(KeyError, match="suffix"):
            reg.parse(parser, [], cfg_override={"output": {"dir": "artifacts/?(model.name)/?(suffix)"}})

    def test_accepts_explicit_dependencies_for_current_value_template(self):
        reg = ConfigRegistry()
        reg.register("model.name", category=str, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default="resnet")
        reg.register("suffix", category=str, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default="ckpt")
        reg.register(
            "output.dir",
            category=str,
            source=ConfigEntrySource.CALLBACK,
            callback=CurrentValueInterpolationCallback(
                "runs/?(model.name)",
                dependency=["model.name", "suffix"],
            ),
        )

        parser = create_parser(reg)
        reg.parse(parser, [], cfg_override={"output": {"dir": "artifacts/?(model.name)/?(suffix)"}})

        assert reg.config["output"]["dir"] == "artifacts/resnet/ckpt"
