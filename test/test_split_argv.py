"""
Unit tests for split_argv_by_cfg function
"""
import pytest
from config_reg.reg import split_argv_by_cfg


class TestSplitArgvByCfg:
    """Tests for split_argv_by_cfg function"""

    def test_basic_with_short_flag(self):
        """Test basic case with -c flag"""
        result = split_argv_by_cfg(['--a', '1', '-c', 'f.yaml', '--b', '2'])
        expected = [('args', ['--a', '1']), ('cfg', 'f.yaml'), ('args', ['--b', '2'])]
        assert result == expected

    def test_basic_with_long_flag(self):
        """Test basic case with --cfg flag"""
        result = split_argv_by_cfg(['--a', '1', '--cfg', 'f.yaml', '--b', '2'])
        expected = [('args', ['--a', '1']), ('cfg', 'f.yaml'), ('args', ['--b', '2'])]
        assert result == expected

    def test_cfg_equals_format(self):
        """Test --cfg= format"""
        result = split_argv_by_cfg(['--a', '1', '--cfg=f.yaml', '--b', '2'])
        expected = [('args', ['--a', '1']), ('cfg', 'f.yaml'), ('args', ['--b', '2'])]
        assert result == expected

    def test_cfg_at_start(self):
        """Test config file at the beginning"""
        result = split_argv_by_cfg(['-c', 'f.yaml', '--a', '1'])
        expected = [('cfg', 'f.yaml'), ('args', ['--a', '1'])]
        assert result == expected

    def test_cfg_at_end(self):
        """Test config file at the end"""
        result = split_argv_by_cfg(['--a', '1', '-c', 'f.yaml'])
        expected = [('args', ['--a', '1']), ('cfg', 'f.yaml')]
        assert result == expected

    def test_only_config_files(self):
        """Test with only config files"""
        result = split_argv_by_cfg(['-c', 'f1.yaml', '--cfg', 'f2.yaml'])
        expected = [('cfg', 'f1.yaml'), ('cfg', 'f2.yaml')]
        assert result == expected

    def test_only_args(self):
        """Test with only arguments"""
        result = split_argv_by_cfg(['--a', '1', '--b', '2'])
        expected = [('args', ['--a', '1', '--b', '2'])]
        assert result == expected

    def test_empty_list(self):
        """Test with empty list"""
        result = split_argv_by_cfg([])
        expected = []
        assert result == expected

    def test_multiple_configs_interleaved(self):
        """Test multiple config files interleaved with arguments"""
        result = split_argv_by_cfg(['--a', '1', '-c', 'f1.yaml', '--b', '2', '--cfg=f2.yaml', '--c', '3'])
        expected = [('args', ['--a', '1']), ('cfg', 'f1.yaml'), ('args', ['--b', '2']), ('cfg', 'f2.yaml'),
                    ('args', ['--c', '3'])]
        assert result == expected

    def test_consecutive_configs(self):
        """Test consecutive config files without args in between"""
        result = split_argv_by_cfg(['--a', '1', '-c', 'f1.yaml', '-c', 'f2.yaml', '--b', '2'])
        expected = [('args', ['--a', '1']), ('cfg', 'f1.yaml'), ('cfg', 'f2.yaml'), ('args', ['--b', '2'])]
        assert result == expected

    def test_missing_config_path_short(self):
        """Test missing config file path after -c"""
        with pytest.raises(ValueError, match="Missing config file path after -c"):
            split_argv_by_cfg(['--a', '1', '-c'])

    def test_missing_config_path_long(self):
        """Test missing config file path after --cfg"""
        with pytest.raises(ValueError, match="Missing config file path after --cfg"):
            split_argv_by_cfg(['--a', '1', '--cfg'])

    def test_empty_cfg_equals(self):
        """Test empty path in --cfg="""
        with pytest.raises(ValueError, match="Empty config file path"):
            split_argv_by_cfg(['--a', '1', '--cfg='])

    def test_mixed_formats(self):
        """Test mixing -c, --cfg, and --cfg= formats"""
        result = split_argv_by_cfg(['-c', 'a.yaml', '--cfg', 'b.yaml', '--cfg=c.yaml'])
        expected = [('cfg', 'a.yaml'), ('cfg', 'b.yaml'), ('cfg', 'c.yaml')]
        assert result == expected

    def test_config_with_path(self):
        """Test config file with path"""
        result = split_argv_by_cfg(['-c', '/path/to/config.yaml', '--a', '1'])
        expected = [('cfg', '/path/to/config.yaml'), ('args', ['--a', '1'])]
        assert result == expected

    def test_config_with_relative_path(self):
        """Test config file with relative path"""
        result = split_argv_by_cfg(['-c', '../configs/base.yml', '--b', '2'])
        expected = [('cfg', '../configs/base.yml'), ('args', ['--b', '2'])]
        assert result == expected

    def test_double_dash_terminator(self):
        """Test -- stops config file parsing"""
        result = split_argv_by_cfg(['--a', '1', '--', '-c', 'not_config', '--cfg', 'also_not'])
        expected = [('args', ['--a', '1', '--', '-c', 'not_config', '--cfg', 'also_not'])]
        assert result == expected

    def test_double_dash_with_cfg_before(self):
        """Test -- after config file"""
        result = split_argv_by_cfg(['-c', 'config.yaml', '--', '-c', 'not_config'])
        expected = [('cfg', 'config.yaml'), ('args', ['--', '-c', 'not_config'])]
        assert result == expected

    def test_double_dash_at_start(self):
        """Test -- at the beginning"""
        result = split_argv_by_cfg(['--', '-c', 'not_config', '--a', '1'])
        expected = [('args', ['--', '-c', 'not_config', '--a', '1'])]
        assert result == expected

    def test_suspicious_option_warning(self, caplog):
        """Test warning when config file path looks like an option"""
        import logging
        with caplog.at_level(logging.WARNING):
            result = split_argv_by_cfg(['-c', '--verbose'])
        assert result == [('cfg', '--verbose')]
        assert "looks like an option" in caplog.text

    def test_suspicious_option_short_flag_warning(self, caplog):
        """Test warning for short option as config path"""
        import logging
        with caplog.at_level(logging.WARNING):
            result = split_argv_by_cfg(['--cfg', '-v'])
        assert result == [('cfg', '-v')]
        assert "looks like an option" in caplog.text

    def test_cfg_equals_suspicious_warning(self, caplog):
        """Test warning for --cfg= with option-like value"""
        import logging
        with caplog.at_level(logging.WARNING):
            result = split_argv_by_cfg(['--cfg=--debug'])
        assert result == [('cfg', '--debug')]
        assert "looks like an option" in caplog.text

    def test_cfg_after_double_dash_warning(self, caplog):
        """Test warning when -c appears after --"""
        import logging
        with caplog.at_level(logging.WARNING):
            result = split_argv_by_cfg(['--', '-c', 'file.yaml'])
        assert result == [('args', ['--', '-c', 'file.yaml'])]
        assert "after '--'" in caplog.text
