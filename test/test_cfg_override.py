"""Tests for cfg_override feature."""

import argparse
import pytest

from config_reg import ConfigRegistry, ConfigEntrySource
from config_reg.callback import ConfigEntryCallback


class TestCfgOverride:
    """Tests for cfg_override in parse()."""

    def test_override_with_nested_dict(self):
        reg = ConfigRegistry()
        reg.register("model.lr", category=float, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default=0.001)
        reg.register("model.batch_size", category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default=16)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, [], cfg_override={"model": {"lr": 0.01, "batch_size": 32}})

        assert reg.config["model"]["lr"] == 0.01
        assert reg.config["model"]["batch_size"] == 32

    def test_override_deeply_nested(self):
        """Override should work with deeply nested structures."""
        reg = ConfigRegistry()
        reg.register("model.encoder.hidden_size",
                     category=int,
                     source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG,
                     default=256)
        reg.register("model.encoder.num_layers",
                     category=int,
                     source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG,
                     default=4)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, [], cfg_override={"model": {"encoder": {"hidden_size": 512, "num_layers": 8}}})

        assert reg.config["model"]["encoder"]["hidden_size"] == 512
        assert reg.config["model"]["encoder"]["num_layers"] == 8

    def test_override_type_casting(self):
        """Override values should be type-casted according to category."""
        reg = ConfigRegistry()
        reg.register("model.lr", category=float, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default=0.001)
        reg.register("model.batch_size", category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default=16)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        # Pass string values that need type casting
        reg.parse(parser, [], cfg_override={"model": {"lr": "0.01", "batch_size": "32"}})

        assert reg.config["model"]["lr"] == 0.01
        assert isinstance(reg.config["model"]["lr"], float)
        assert reg.config["model"]["batch_size"] == 32
        assert isinstance(reg.config["model"]["batch_size"], int)

    def test_override_unregistered_key_ignored(self):
        """Unregistered keys in override should be silently ignored."""
        reg = ConfigRegistry()
        reg.register("model.lr", category=float, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default=0.001)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        # Include an unregistered key
        reg.parse(parser, [], cfg_override={"model": {"lr": 0.01, "unknown": 123}})

        assert reg.config["model"]["lr"] == 0.01
        assert "unknown" not in reg.config["model"]

    def test_warn_unknown_key_disabled_by_default(self, caplog):
        """By default, unknown keys should not trigger a warning."""
        import logging
        reg = ConfigRegistry()
        reg.register("model.lr", category=float, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default=0.001)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        with caplog.at_level(logging.WARNING):
            reg.parse(parser, [], cfg_override={"model": {"lr": 0.01, "unknown": 123}})

        assert "Unknown keys" not in caplog.text

    def test_warn_unknown_key_via_init(self, caplog):
        """Unknown keys should trigger warning when warn_unknown_key=True in init."""
        import logging
        reg = ConfigRegistry(warn_unknown_key=True)
        reg.register("model.lr", category=float, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default=0.001)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        with caplog.at_level(logging.WARNING):
            reg.parse(parser, [], cfg_override={"model": {"lr": 0.01, "unknown": 123}})

        assert "Unknown keys" in caplog.text
        assert "model.unknown" in caplog.text

    def test_warn_unknown_key_via_parse(self, caplog):
        """Unknown keys should trigger warning when warn_unknown_key=True in parse()."""
        import logging
        reg = ConfigRegistry()  # Default is False
        reg.register("model.lr", category=float, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default=0.001)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        with caplog.at_level(logging.WARNING):
            reg.parse(parser, [], cfg_override={"model": {"lr": 0.01, "unknown": 123}}, warn_unknown_key=True)

        assert "Unknown keys" in caplog.text
        assert "model.unknown" in caplog.text

    def test_warn_unknown_key_parse_overrides_init(self, caplog):
        """Per-call warn_unknown_key should override instance attribute."""
        import logging
        reg = ConfigRegistry(warn_unknown_key=True)  # Instance default is True
        reg.register("model.lr", category=float, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default=0.001)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        # Override to False in parse()
        with caplog.at_level(logging.WARNING):
            reg.parse(parser, [], cfg_override={"model": {"lr": 0.01, "unknown": 123}}, warn_unknown_key=False)

        assert "Unknown keys" not in caplog.text

    def test_warn_unknown_key_dict_type_children_not_warned(self, caplog):
        """Children of dict-type registered keys should not trigger warnings."""
        import logging
        from config_reg.type_def import ConfigEntryCommandlineMapPattern

        reg = ConfigRegistry(warn_unknown_key=True)
        reg.register("model.lr", category=float, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default=0.001)
        # Register a dict-type key
        reg.register("model.params",
                     category=dict[str, int],
                     source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG,
                     cmdpattern=ConfigEntryCommandlineMapPattern.COMMA_SEP_COLON)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        with caplog.at_level(logging.WARNING):
            # model.params children (any_key, another_key) should not be warned
            # model.unknown should be warned
            reg.parse(parser, [],
                      cfg_override={"model": {
                          "lr": 0.01,
                          "params": {
                              "any_key": 1,
                              "another_key": 2
                          },
                          "unknown": 123
                      }})

        assert "model.unknown" in caplog.text
        assert "model.params.any_key" not in caplog.text
        assert "model.params.another_key" not in caplog.text

    def test_override_ignores_source_constraint(self):
        """Override should work regardless of source constraint."""
        reg = ConfigRegistry()
        # CONFIG_ONLY normally can't be set via commandline, but override should work
        reg.register("model.lr", category=float, source=ConfigEntrySource.CONFIG_ONLY, default=0.001)
        # COMMANDLINE_ONLY normally can't be set via config file, but override should work
        reg.register("model.batch_size", category=int, source=ConfigEntrySource.COMMANDLINE_ONLY, default=16)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, [], cfg_override={"model": {"lr": 0.01, "batch_size": 32}})

        assert reg.config["model"]["lr"] == 0.01
        assert reg.config["model"]["batch_size"] == 32

    def test_override_after_config_file(self, tmp_path):
        """Override should be applied after config file, overriding its values."""
        # Create a temp config file
        config_file = tmp_path / "config.yaml"
        config_file.write_text("model:\n  lr: 0.005\n  batch_size: 64\n")

        reg = ConfigRegistry()
        reg.register("model.lr", category=float, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default=0.001)
        reg.register("model.batch_size", category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default=16)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        # Parse with config file, then override lr
        reg.parse(parser, ["-c", str(config_file)], cfg_override={"model": {"lr": 0.01}})

        assert reg.config["model"]["lr"] == 0.01  # Overridden
        assert reg.config["model"]["batch_size"] == 64  # From config file

    def test_override_after_cmdline(self):
        """Override should be applied after cmdline args, overriding them."""
        reg = ConfigRegistry()
        reg.register("model.lr", category=float, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default=0.001)
        reg.register("model.batch_size", category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default=16)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        # Parse with cmdline args, then override lr
        reg.parse(parser, ["--model.lr", "0.005", "--model.batch_size", "64"], cfg_override={"model": {"lr": 0.01}})

        assert reg.config["model"]["lr"] == 0.01  # Overridden
        assert reg.config["model"]["batch_size"] == 64  # From cmdline

    def test_override_partial(self):
        """Override should only affect specified keys, leaving others unchanged."""
        reg = ConfigRegistry()
        reg.register("model.lr", category=float, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default=0.001)
        reg.register("model.batch_size", category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default=16)
        reg.register("model.epochs", category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default=100)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        # Only override lr, batch_size and epochs should keep defaults
        reg.parse(parser, [], cfg_override={"model": {"lr": 0.01}})

        assert reg.config["model"]["lr"] == 0.01
        assert reg.config["model"]["batch_size"] == 16  # Default
        assert reg.config["model"]["epochs"] == 100  # Default


class TestCfgOverrideWithCallback:
    """Tests for cfg_override interaction with callbacks."""

    def test_callback_receives_overridden_value(self):
        """Callbacks should receive the overridden value in their dependencies."""
        received_values = {}

        class RecordingCallback(ConfigEntryCallback):
            dependency = ["model.lr"]
            always = True

            def __call__(self, curr_key, curr_value, prog, dep):
                received_values["lr"] = dep["model.lr"]
                return curr_value if curr_value is not None else 0

        reg = ConfigRegistry()
        reg.register("model.lr", category=float, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default=0.001)
        reg.register("model.computed", category=float, source=ConfigEntrySource.CALLBACK, callback=RecordingCallback())

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, [], cfg_override={"model": {"lr": 0.01}})

        assert received_values["lr"] == 0.01

    def test_callback_computes_from_overridden_value(self):
        """Callbacks should compute based on overridden values."""

        class DoubleCallback(ConfigEntryCallback):
            dependency = ["model.lr"]
            always = True

            def __call__(self, curr_key, curr_value, prog, dep):
                return dep["model.lr"] * 2

        reg = ConfigRegistry()
        reg.register("model.lr", category=float, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default=0.001)
        reg.register("model.lr_doubled", category=float, source=ConfigEntrySource.CALLBACK, callback=DoubleCallback())

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, [], cfg_override={"model": {"lr": 0.01}})

        assert reg.config["model"]["lr_doubled"] == 0.02

    def test_override_does_not_affect_callback_entry_directly(self):
        """Override on a CALLBACK source entry is applied but callback runs after."""

        class FixedCallback(ConfigEntryCallback):
            dependency = []
            always = True

            def __call__(self, curr_key, curr_value, prog, dep):
                return 999.0

        reg = ConfigRegistry()
        reg.register("model.computed", category=float, source=ConfigEntrySource.CALLBACK, callback=FixedCallback())

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        # Even if we try to override a CALLBACK entry, the callback runs after and sets the final value
        reg.parse(parser, [], cfg_override={"model": {"computed": 123.0}})

        # Callback runs after override, so callback's return value is the final value
        assert reg.config["model"]["computed"] == 999.0


class TestCfgOverrideNoParser:
    """Tests for cfg_override when parser is None."""

    def test_override_without_parser(self):
        """Override should work even without a parser."""
        reg = ConfigRegistry()
        reg.register("model.lr", category=float, source=ConfigEntrySource.CONFIG_ONLY, default=0.001)
        reg.register("model.batch_size", category=int, source=ConfigEntrySource.CONFIG_ONLY, default=16)

        reg.parse(None, cfg_override={"model": {"lr": 0.01, "batch_size": 32}})

        assert reg.config["model"]["lr"] == 0.01
        assert reg.config["model"]["batch_size"] == 32
