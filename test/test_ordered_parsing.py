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

    def test_bool_set_false_after_config(self, temp_config_dir):
        """Test: SET_FALSE bool after config"""
        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'flag': True})

        reg = ConfigRegistry()
        reg.register('flag',
                     category=bool,
                     source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG,
                     cmdpattern=ConfigEntryCommandlineBoolPattern.SET_FALSE)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, ['-c', cfg1_path, '--flag'], strict=False)

        assert reg.select()['flag'] is False  # --flag sets to False, overrides config

    def test_bool_set_false_before_config(self, temp_config_dir):
        """Test: SET_FALSE bool before config"""
        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'flag': False})

        reg = ConfigRegistry()
        reg.register('flag',
                     category=bool,
                     source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG,
                     cmdpattern=ConfigEntryCommandlineBoolPattern.SET_FALSE)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        # --flag sets to False, but config (also False) comes after
        reg.parse(parser, ['--flag', '-c', cfg1_path], strict=False)

        assert reg.select()['flag'] is False  # config overrides --flag

    def test_bool_on_off_enable(self, temp_config_dir):
        """Test: ON_OFF pattern with --flag (sets to True)"""
        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'flag': False})

        reg = ConfigRegistry()
        reg.register('flag',
                     category=bool,
                     source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG,
                     cmdpattern=ConfigEntryCommandlineBoolPattern.ON_OFF)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, ['-c', cfg1_path, '--flag'], strict=False)

        assert reg.select()['flag'] is True  # --flag enables, overrides config

    def test_bool_with_default_no_config(self, temp_config_dir):
        """Test: bool with default, no config file"""
        reg = ConfigRegistry()
        reg.register('flag',
                     category=bool,
                     source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG,
                     default=True,
                     cmdpattern=ConfigEntryCommandlineBoolPattern.SET_TRUE)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, [], strict=False)

        assert reg.select()['flag'] is True  # default value

    def test_bool_unspecified_keeps_config(self, temp_config_dir):
        """Test: bool not specified on cmdline keeps config value"""
        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'flag': True, 'other': 10})

        reg = ConfigRegistry()
        reg.register('flag',
                     category=bool,
                     source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG,
                     cmdpattern=ConfigEntryCommandlineBoolPattern.SET_TRUE)
        reg.register('other', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        # Don't specify --flag, only --other
        reg.parse(parser, ['-c', cfg1_path, '--other', '99'], strict=False)

        assert reg.select()['flag'] is True  # keeps config value
        assert reg.select()['other'] == 99

    def test_bool_multiple_configs_override(self, temp_config_dir):
        """Test: later config overrides earlier bool value"""
        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'flag': True})
        cfg2_path = create_yaml_file(temp_config_dir, 'cfg2.yaml', {'flag': False})

        reg = ConfigRegistry()
        reg.register('flag',
                     category=bool,
                     source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG,
                     cmdpattern=ConfigEntryCommandlineBoolPattern.SET_TRUE)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, ['-c', cfg1_path, '-c', cfg2_path], strict=False)

        assert reg.select()['flag'] is False  # cfg2 overrides cfg1

    def test_bool_on_off_no_default_no_flag(self):
        """Test: ON_OFF pattern without default, no flag provided - returns Unspecified"""
        reg = ConfigRegistry()
        reg.register(
            'flag',
            category=bool,
            source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG,
            required=True,  # Mark as required
            cmdpattern=ConfigEntryCommandlineBoolPattern.ON_OFF)
        # No default is set

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        # Neither --flag nor --flag__off is provided, no config file
        # With strict=True and required=True, this should raise ValueError
        with pytest.raises(ValueError, match="unspecified value in config"):
            reg.parse(parser, [], strict=True)

    def test_bool_on_off_no_default_no_flag_non_strict(self):
        """Test: ON_OFF pattern without default, no flag, non-strict mode"""
        reg = ConfigRegistry()
        reg.register('flag',
                     category=bool,
                     source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG,
                     cmdpattern=ConfigEntryCommandlineBoolPattern.ON_OFF)
        # No default is set

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        # Neither --flag nor --flag__off is provided, no config file
        # With strict=False, should complete but value is Unspecified
        reg.parse(parser, [], strict=False)

        result = reg.select()
        # The key exists in result, but value is ConfigEntryValueUnspecified
        assert 'flag' in result
        assert result['flag'] is ConfigEntryValueUnspecified

        # After strip, the key should be removed
        result_stripped = reg.select(strip=True)
        assert 'flag' not in result_stripped


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

    def test_deep_nested_keys(self, temp_config_dir):
        """Test: deep nesting like a.b.c.d"""
        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'a': {'b': {'c': {'d': 1, 'e': 2}}}})

        reg = ConfigRegistry()
        reg.register('a.b.c.d', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)
        reg.register('a.b.c.e', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, ['-c', cfg1_path, '--a.b.c.d', '100'], strict=False)

        assert reg.select()['a']['b']['c']['d'] == 100
        assert reg.select()['a']['b']['c']['e'] == 2

    def test_nested_partial_override_multiple_configs(self, temp_config_dir):
        """Test: partial override with multiple config files"""
        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml',
                                     {'model': {
                                         'lr': 0.001,
                                         'batch_size': 32,
                                         'hidden': 256
                                     }})
        cfg2_path = create_yaml_file(
            temp_config_dir,
            'cfg2.yaml',
            {
                'model': {
                    'lr': 0.01
                }  # only override lr
            })

        reg = ConfigRegistry()
        reg.register('model.lr', category=float, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)
        reg.register('model.batch_size', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)
        reg.register('model.hidden', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, ['-c', cfg1_path, '-c', cfg2_path], strict=False)

        assert reg.select()['model']['lr'] == 0.01  # from cfg2
        assert reg.select()['model']['batch_size'] == 32  # from cfg1
        assert reg.select()['model']['hidden'] == 256  # from cfg1

    def test_nested_cmdline_only(self, temp_config_dir):
        """Test: nested keys with COMMANDLINE_ONLY source"""
        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'train': {'epochs': 100, 'verbose': True}})

        reg = ConfigRegistry()
        reg.register('train.epochs', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)
        reg.register('train.verbose',
                     category=bool,
                     source=ConfigEntrySource.COMMANDLINE_ONLY,
                     cmdpattern=ConfigEntryCommandlineBoolPattern.SET_TRUE)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        # train.verbose from config should be ignored (COMMANDLINE_ONLY)
        reg.parse(parser, ['-c', cfg1_path, '--train.verbose'], strict=False)

        assert reg.select()['train']['epochs'] == 100
        assert reg.select()['train']['verbose'] is True  # from cmdline, not config

    def test_nested_with_defaults(self, temp_config_dir):
        """Test: nested keys with default values"""
        reg = ConfigRegistry()
        reg.register('model.lr', category=float, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default=0.001)
        reg.register('model.batch_size', category=int, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG, default=32)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, ['--model.batch_size', '64'], strict=False)

        assert reg.select()['model']['lr'] == 0.001  # default
        assert reg.select()['model']['batch_size'] == 64  # cmdline

    def test_nested_config_before_cmdline(self, temp_config_dir):
        """Test: nested key cmdline before config gets overridden"""
        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'opt': {'learning_rate': 0.1}})

        reg = ConfigRegistry()
        reg.register('opt.learning_rate', category=float, source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        # cmdline before config, so config should win
        reg.parse(parser, ['--opt.learning_rate', '0.001', '-c', cfg1_path], strict=False)

        assert reg.select()['opt']['learning_rate'] == 0.1  # config overrides


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


class TestListTypes:
    """Tests for list type entries"""

    def test_list_from_config(self, temp_config_dir):
        """Test: list values from config file"""
        from config_reg.type_def import ConfigEntryCommandlineSeqPattern

        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'items': [1, 2, 3]})

        reg = ConfigRegistry()
        reg.register('items',
                     category=list[int],
                     source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG,
                     cmdpattern=ConfigEntryCommandlineSeqPattern.COMMA_SEP)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, ['-c', cfg1_path], strict=False)

        assert reg.select()['items'] == [1, 2, 3]

    def test_list_cmdline_comma_sep(self, temp_config_dir):
        """Test: list from cmdline with comma separator"""
        from config_reg.type_def import ConfigEntryCommandlineSeqPattern

        reg = ConfigRegistry()
        reg.register('items',
                     category=list[int],
                     source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG,
                     cmdpattern=ConfigEntryCommandlineSeqPattern.COMMA_SEP)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, ['--items', '1,2,3,4'], strict=False)

        assert reg.select()['items'] == [1, 2, 3, 4]

    def test_list_cmdline_colon_sep(self, temp_config_dir):
        """Test: list from cmdline with colon separator"""
        from config_reg.type_def import ConfigEntryCommandlineSeqPattern

        reg = ConfigRegistry()
        reg.register('paths',
                     category=list[str],
                     source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG,
                     cmdpattern=ConfigEntryCommandlineSeqPattern.COLON_SEP)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, ['--paths', '/path/a:/path/b:/path/c'], strict=False)

        assert reg.select()['paths'] == ['/path/a', '/path/b', '/path/c']

    def test_list_cmdline_override_config(self, temp_config_dir):
        """Test: cmdline list overrides config list"""
        from config_reg.type_def import ConfigEntryCommandlineSeqPattern

        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'nums': [10, 20, 30]})

        reg = ConfigRegistry()
        reg.register('nums',
                     category=list[int],
                     source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG,
                     cmdpattern=ConfigEntryCommandlineSeqPattern.COMMA_SEP)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, ['-c', cfg1_path, '--nums', '1,2'], strict=False)

        assert reg.select()['nums'] == [1, 2]  # cmdline overrides config

    def test_list_config_override_cmdline(self, temp_config_dir):
        """Test: config list overrides earlier cmdline list"""
        from config_reg.type_def import ConfigEntryCommandlineSeqPattern

        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'nums': [10, 20, 30]})

        reg = ConfigRegistry()
        reg.register('nums',
                     category=list[int],
                     source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG,
                     cmdpattern=ConfigEntryCommandlineSeqPattern.COMMA_SEP)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, ['--nums', '1,2', '-c', cfg1_path], strict=False)

        assert reg.select()['nums'] == [10, 20, 30]  # config overrides cmdline

    def test_list_string_type(self, temp_config_dir):
        """Test: list of strings from config"""
        from config_reg.type_def import ConfigEntryCommandlineSeqPattern

        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'tags': ['alpha', 'beta', 'gamma']})

        reg = ConfigRegistry()
        reg.register('tags',
                     category=list[str],
                     source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG,
                     cmdpattern=ConfigEntryCommandlineSeqPattern.COMMA_SEP)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, ['-c', cfg1_path], strict=False)

        assert reg.select()['tags'] == ['alpha', 'beta', 'gamma']

    def test_list_empty_from_config(self, temp_config_dir):
        """Test: empty list from config"""
        from config_reg.type_def import ConfigEntryCommandlineSeqPattern

        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'items': []})

        reg = ConfigRegistry()
        reg.register('items',
                     category=list[int],
                     source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG,
                     cmdpattern=ConfigEntryCommandlineSeqPattern.COMMA_SEP)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, ['-c', cfg1_path], strict=False)

        assert reg.select()['items'] == []

    def test_nested_list(self, temp_config_dir):
        """Test: list in nested key"""
        from config_reg.type_def import ConfigEntryCommandlineSeqPattern

        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'data': {'ids': [1, 2, 3]}})

        reg = ConfigRegistry()
        reg.register('data.ids',
                     category=list[int],
                     source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG,
                     cmdpattern=ConfigEntryCommandlineSeqPattern.COMMA_SEP)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, ['-c', cfg1_path, '--data.ids', '4,5,6'], strict=False)

        assert reg.select()['data']['ids'] == [4, 5, 6]


class TestDictTypes:
    """Tests for dict type entries"""

    def test_dict_from_config(self, temp_config_dir):
        """Test: dict values from config file"""
        from config_reg.type_def import ConfigEntryCommandlineMapPattern

        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'params': {'a': 1, 'b': 2}})

        reg = ConfigRegistry()
        reg.register('params',
                     category=dict[str, int],
                     source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG,
                     cmdpattern=ConfigEntryCommandlineMapPattern.COMMA_SEP_COLON)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, ['-c', cfg1_path], strict=False)

        assert reg.select()['params'] == {'a': 1, 'b': 2}

    def test_dict_cmdline_comma_colon(self, temp_config_dir):
        """Test: dict from cmdline with comma-colon pattern"""
        from config_reg.type_def import ConfigEntryCommandlineMapPattern

        reg = ConfigRegistry()
        reg.register('params',
                     category=dict[str, int],
                     source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG,
                     cmdpattern=ConfigEntryCommandlineMapPattern.COMMA_SEP_COLON)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, ['--params', 'x:10,y:20,z:30'], strict=False)

        assert reg.select()['params'] == {'x': 10, 'y': 20, 'z': 30}

    def test_dict_cmdline_override_config(self, temp_config_dir):
        """Test: cmdline dict overrides config dict"""
        from config_reg.type_def import ConfigEntryCommandlineMapPattern

        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'opts': {'key1': 'val1', 'key2': 'val2'}})

        reg = ConfigRegistry()
        reg.register('opts',
                     category=dict[str, str],
                     source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG,
                     cmdpattern=ConfigEntryCommandlineMapPattern.COMMA_SEP_COLON)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, ['-c', cfg1_path, '--opts', 'new:value'], strict=False)

        assert reg.select()['opts'] == {'new': 'value'}  # cmdline overrides config

    def test_dict_config_override_cmdline(self, temp_config_dir):
        """Test: config dict overrides earlier cmdline dict"""
        from config_reg.type_def import ConfigEntryCommandlineMapPattern

        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'opts': {'from': 'config'}})

        reg = ConfigRegistry()
        reg.register('opts',
                     category=dict[str, str],
                     source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG,
                     cmdpattern=ConfigEntryCommandlineMapPattern.COMMA_SEP_COLON)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, ['--opts', 'from:cmdline', '-c', cfg1_path], strict=False)

        assert reg.select()['opts'] == {'from': 'config'}  # config overrides cmdline

    def test_dict_string_value(self, temp_config_dir):
        """Test: dict with string values from config"""
        from config_reg.type_def import ConfigEntryCommandlineMapPattern

        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'env': {'HOME': '/home/user', 'PATH': '/usr/bin'}})

        reg = ConfigRegistry()
        reg.register('env',
                     category=dict[str, str],
                     source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG,
                     cmdpattern=ConfigEntryCommandlineMapPattern.COMMA_SEP_COLON)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, ['-c', cfg1_path], strict=False)

        assert reg.select()['env'] == {'HOME': '/home/user', 'PATH': '/usr/bin'}

    def test_dict_empty_from_config(self, temp_config_dir):
        """Test: empty dict from config"""
        from config_reg.type_def import ConfigEntryCommandlineMapPattern

        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'params': {}})

        reg = ConfigRegistry()
        reg.register('params',
                     category=dict[str, int],
                     source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG,
                     cmdpattern=ConfigEntryCommandlineMapPattern.COMMA_SEP_COLON)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, ['-c', cfg1_path], strict=False)

        assert reg.select()['params'] == {}

    def test_nested_dict(self, temp_config_dir):
        """Test: dict in nested key"""
        from config_reg.type_def import ConfigEntryCommandlineMapPattern

        cfg1_path = create_yaml_file(temp_config_dir, 'cfg1.yaml', {'config': {'options': {'a': 1, 'b': 2}}})

        reg = ConfigRegistry()
        reg.register('config.options',
                     category=dict[str, int],
                     source=ConfigEntrySource.COMMANDLINE_OVER_CONFIG,
                     cmdpattern=ConfigEntryCommandlineMapPattern.COMMA_SEP_COLON)

        parser = argparse.ArgumentParser()
        reg.hook(parser)

        reg.parse(parser, ['-c', cfg1_path, '--config.options', 'c:3,d:4'], strict=False)

        assert reg.select()['config']['options'] == {'c': 3, 'd': 4}
