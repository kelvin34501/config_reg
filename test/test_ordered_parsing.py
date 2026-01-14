"""
Integration tests for ordered parsing of config files and command-line arguments
"""
import pytest
import argparse
import tempfile
import os
import yaml

from config_reg import ConfigRegistry
from config_reg.type_def import (
    ConfigEntrySource,
    ConfigEntryCommandlineBoolPattern,
    ConfigEntryValueUnspecified,
)


@pytest.fixture
def temp_config_dir():
    """Create a temporary directory for config files"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def create_yaml_file(directory, filename, content):
    """Helper to create a yaml config file"""
    filepath = os.path.join(directory, filename)
    with open(filepath, 'w') as f:
        yaml.dump(content, f)
    return filepath


class TestOrderedParsing:
    """Tests for ordered parsing behavior"""

    def test_args_before_config(self, temp_config_dir):
        """Test: args set before config file should be overridden by config"""
        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'a': 10, 'b': 20})

        reg = ConfigRegistry()
        reg.register('a', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)
        reg.register('b', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        # --a 1 comes before config, so config should override it
        reg.parse(parser, ['--a', '1', '-c', cfg1_path], strict=False)

        assert reg.select()['a'] == 10  # cfg1 overrides --a 1
        assert reg.select()['b'] == 20

    def test_args_after_config(self, temp_config_dir):
        """Test: args set after config file should override config"""
        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'a': 10, 'b': 20})

        reg = ConfigRegistry()
        reg.register('a', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)
        reg.register('b', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        # config comes before --a 1, so --a 1 should override config
        reg.parse(parser, ['-c', cfg1_path, '--a', '1'], strict=False)

        assert reg.select()['a'] == 1  # --a 1 overrides cfg1
        assert reg.select()['b'] == 20

    def test_interleaved_args_and_config(self, temp_config_dir):
        """Test: args → config → args pattern"""
        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'a': 10, 'b': 20, 'c': 30})

        reg = ConfigRegistry()
        reg.register('a', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)
        reg.register('b', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)
        reg.register('c', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        # --a 1 is before config (overridden), --b 200 is after config (overrides)
        reg.parse(parser, ['--a', '1', '-c', cfg1_path, '--b', '200'], strict=False)

        assert reg.select()['a'] == 10  # cfg1 overrides --a 1
        assert reg.select()['b'] == 200  # --b 200 overrides cfg1
        assert reg.select()['c'] == 30  # from cfg1

    def test_multiple_config_files(self, temp_config_dir):
        """Test: multiple config files override each other"""
        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'a': 10, 'b': 20})
        cfg2_path = create_yaml_file(temp_config_dir, 'cfg2.yaml', {'a': 100})

        reg = ConfigRegistry()
        reg.register('a', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)
        reg.register('b', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, ['-c', cfg1_path, '-c', cfg2_path], strict=False)

        assert reg.select()['a'] == 100  # cfg2 overrides cfg1
        assert reg.select()['b'] == 20  # from cfg1 (cfg2 doesn't have b)

    def test_config_between_args(self, temp_config_dir):
        """Test: config file between two arguments"""
        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'a': 10, 'b': 20})

        reg = ConfigRegistry()
        reg.register('a', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)
        reg.register('b', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        # Both args are after config, so both should override
        reg.parse(parser, ['-c', cfg1_path, '--a', '1', '--b', '2'], strict=False)

        assert reg.select()['a'] == 1
        assert reg.select()['b'] == 2

    def test_complex_interleaved(self, temp_config_dir):
        """Test: complex interleaving pattern"""
        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'a': 10, 'b': 20, 'c': 30})
        cfg2_path = create_yaml_file(temp_config_dir, 'cfg2.yaml', {'b': 200, 'c': 300})

        reg = ConfigRegistry()
        reg.register('a', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)
        reg.register('b', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)
        reg.register('c', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        # --a 1 → cfg1 → --b 99 → cfg2 → --c 999
        reg.parse(parser, ['--a', '1', '-c', cfg1_path, '--b', '99', '--cfg', cfg2_path, '--c', '999'], strict=False)

        assert reg.select()['a'] == 10  # cfg1 overrides --a 1
        assert reg.select()['b'] == 200  # cfg2 overrides --b 99
        assert reg.select()['c'] == 999  # --c 999 overrides cfg2

    def test_cfg_equals_format(self, temp_config_dir):
        """Test: --cfg= format"""
        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'a': 10})

        reg = ConfigRegistry()
        reg.register('a', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, [f'--cfg={cfg1_path}'], strict=False)

        assert reg.select()['a'] == 10

    def test_only_args_no_config(self, temp_config_dir):
        """Test: only command-line args, no config files"""
        reg = ConfigRegistry()
        reg.register('a', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)
        reg.register('b', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, ['--a', '1', '--b', '2'], strict=False)

        assert reg.select()['a'] == 1
        assert reg.select()['b'] == 2

    def test_only_config_no_args(self, temp_config_dir):
        """Test: only config files, no command-line args"""
        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'a': 10, 'b': 20})

        reg = ConfigRegistry()
        reg.register('a', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)
        reg.register('b', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, ['-c', cfg1_path], strict=False)

        assert reg.select()['a'] == 10
        assert reg.select()['b'] == 20

    def test_empty_args(self, temp_config_dir):
        """Test: empty argument list"""
        reg = ConfigRegistry()
        reg.register('a', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default=5)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, [], strict=False)

        assert reg.select()['a'] == 5  # default value


class TestBooleanOrdering:
    """Tests for boolean arguments with ordered parsing"""

    def test_bool_set_true_after_config(self, temp_config_dir):
        """Test: SET_TRUE bool after config"""
        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'flag': False})

        reg = ConfigRegistry()
        reg.register('flag',
                     category=bool,
                     source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG,
                     cmdpattern=ConfigEntryCommandlineBoolPattern.SET_TRUE)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, ['-c', cfg1_path, '--flag'], strict=False)

        assert reg.select()['flag'] is True  # --flag overrides config

    def test_bool_set_true_before_config(self, temp_config_dir):
        """Test: SET_TRUE bool before config"""
        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'flag': False})

        reg = ConfigRegistry()
        reg.register('flag',
                     category=bool,
                     source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG,
                     cmdpattern=ConfigEntryCommandlineBoolPattern.SET_TRUE)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, ['--flag', '-c', cfg1_path], strict=False)

        assert reg.select()['flag'] is False  # config overrides --flag

    def test_bool_on_off_pattern(self, temp_config_dir):
        """Test: ON_OFF bool pattern"""
        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'flag': True})

        reg = ConfigRegistry()
        reg.register('flag',
                     category=bool,
                     source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG,
                     cmdpattern=ConfigEntryCommandlineBoolPattern.ON_OFF)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, ['-c', cfg1_path, '--flag__off'], strict=False)

        assert reg.select()['flag'] is False  # --flag__off overrides config


class TestNestedKeys:
    """Tests for nested config keys"""

    def test_nested_key_override(self, temp_config_dir):
        """Test: nested keys like model.lr"""
        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'model': {'lr': 0.001, 'batch_size': 32}})

        reg = ConfigRegistry()
        reg.register('model.lr', category=float, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)
        reg.register('model.batch_size', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, ['-c', cfg1_path, '--model.lr', '0.01'], strict=False)

        assert reg.select()['model']['lr'] == 0.01
        assert reg.select()['model']['batch_size'] == 32


class TestBindDefaultConfig:
    """Tests for bind_default_config_filepath"""

    def test_bind_default_before_cmdline(self, temp_config_dir):
        """Test: bind_default_config_filepath is applied before cmdline parsing"""
        cfg_default = create_yaml_file(temp_config_dir, 'default.yaml', {'a': 5})
        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'a': 10})

        reg = ConfigRegistry()
        reg.register('a', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)

        # Bind default config
        reg.bind_default_config_filepath(cfg_default)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        # Both configs should be applied, but cfg1 comes after
        reg.parse(parser, ['-c', cfg1_path], strict=False)

        assert reg.select()['a'] == 10  # cfg1 overrides default

    def test_bind_default_with_cmdline_override(self, temp_config_dir):
        """Test: cmdline args override bind_default config"""
        cfg_default = create_yaml_file(temp_config_dir, 'default.yaml', {'a': 5})

        reg = ConfigRegistry()
        reg.register('a', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)

        reg.bind_default_config_filepath(cfg_default)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, ['--a', '100'], strict=False)

        assert reg.select()['a'] == 100  # --a overrides default config


class TestConfigOnlyEntries:
    """Tests for CONFIG_ONLY entries"""

    def test_config_only_not_from_cmdline(self, temp_config_dir):
        """Test: CONFIG_ONLY entries are only set from config files"""
        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'a': 10, 'b': 20})

        reg = ConfigRegistry()
        reg.register('a', category=int, source=ConfigEntrySource.CONFIG_ONLY)
        reg.register('b', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        # --a should not be registered (CONFIG_ONLY), only --b
        reg.parse(parser, ['-c', cfg1_path, '--b', '99'], strict=False)

        assert reg.select()['a'] == 10  # from config
        assert reg.select()['b'] == 99  # from cmdline


class TestCommandlineOnlyEntries:
    """Tests for COMMANDLINE_ONLY entries"""

    def test_commandline_only_not_from_config(self, temp_config_dir):
        """Test: COMMANDLINE_ONLY entries ignore config files"""
        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'a': 10})

        reg = ConfigRegistry()
        reg.register('a', category=int, source=ConfigEntrySource.COMMANDLINE_ONLY)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, ['-c', cfg1_path, '--a', '99'], strict=False)

        assert reg.select()['a'] == 99  # COMMANDLINE_ONLY ignores config
