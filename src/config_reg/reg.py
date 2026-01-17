from __future__ import annotations

import logging
import os
import sys
import argparse
from typing import Optional, Union, Any
from typing import Sequence, Mapping
from dataclasses import dataclass

from .type_def import ConfigEntrySource, ConfigEntryValueUnspecified, analyze_type, cast_to_res
from .type_def import (
    ConfigEntryCommandlinePattern,
    ConfigEntryCommandlineSeqPattern,
    ConfigEntryCommandlineMapPattern,
)
from .type_def import supported_by_commandline, proclist_pattern_paired
from .type_def import handle_cmd_seq, handle_cmd_map
from .type_def import hook_cmd_bool, handle_cmd_bool
from .type_transform import is_type

from .index import set_value, index_key, del_value

from .callback import ConfigEntryCallback, resolve_callback_dependency

from .if_yaml import load_yaml

from copy import deepcopy

logger = logging.getLogger(__name__)


def split_argv_by_cfg(argv: list[str]) -> list[tuple[str, any]]:
    """
    Split argv by -c/--cfg markers into segments.

    The '--' marker stops config file parsing; all arguments after '--' are
    treated as regular arguments and '-c/--cfg' will not be interpreted as
    config file markers.

    Returns: [(segment_type, content), ...]
        segment_type: 'args' | 'cfg'
        content:
            - 'args': list[str] - argument list
            - 'cfg': str - config file path

    Example:
        Input: ['--a', '1', '-c', 'f1.yaml', '--b', '2', '--cfg=f2.yaml', '--c', '3']
        Output: [
            ('args', ['--a', '1']),
            ('cfg', 'f1.yaml'),
            ('args', ['--b', '2']),
            ('cfg', 'f2.yaml'),
            ('args', ['--c', '3'])
        ]

        Input: ['--a', '1', '--', '-c', 'not_a_config']
        Output: [
            ('args', ['--a', '1', '--', '-c', 'not_a_config'])
        ]
    """
    segments = []
    current_args = []
    i = 0
    stop_cfg_parsing = False  # Set to True after encountering '--'

    while i < len(argv):
        arg = argv[i]

        # Check for '--' terminator
        if arg == '--':
            current_args.append(arg)
            stop_cfg_parsing = True
            i += 1
            continue

        # After '--', treat everything as regular arguments
        if stop_cfg_parsing:
            # Warn if -c/--cfg appears after '--'
            if arg == '-c' or arg == '--cfg' or arg.startswith('--cfg='):
                logger.warning(f"'{arg}' after '--' will be treated as regular argument, "
                               "not as config file marker")
            current_args.append(arg)
            i += 1
            continue

        # Case 1: -c <file> or --cfg <file> (two tokens)
        if arg == '-c' or arg == '--cfg':
            # Save current accumulated args segment
            if current_args:
                segments.append(('args', current_args))
                current_args = []

            # Get config file path
            if i + 1 < len(argv):
                cfg_file = argv[i + 1]

                # Warn if config file path looks like an option (starts with -)
                # This may indicate the previous argument expected a value
                if cfg_file.startswith('-'):
                    logger.warning(f"Config file path '{cfg_file}' looks like an option. "
                                   f"Did you mean to pass '{cfg_file}' as a value to the previous argument? "
                                   "Use '--' to stop config file parsing if needed.")

                segments.append(('cfg', cfg_file))
                i += 2  # Skip -c and file path
            else:
                raise ValueError(f"Missing config file path after {arg}")

        # Case 2: --cfg=<file> (single token)
        elif arg.startswith('--cfg='):
            if current_args:
                segments.append(('args', current_args))
                current_args = []

            cfg_file = arg[6:]  # Remove '--cfg='
            if not cfg_file:
                raise ValueError("Empty config file path in --cfg=")

            # Warn if config file path looks like an option
            if cfg_file.startswith('-'):
                logger.warning(f"Config file path '{cfg_file}' looks like an option. "
                               "Use '--' to stop config file parsing if needed.")

            segments.append(('cfg', cfg_file))
            i += 1

        # Case 3: regular argument
        else:
            current_args.append(arg)
            i += 1

    # Add final args segment
    if current_args:
        segments.append(('args', current_args))

    return segments


@dataclass
class ConfigEntryAttr:
    source: ConfigEntrySource
    desc: Optional[str]
    category: Union[type, Any]
    cmdpattern: Optional[ConfigEntryCommandlinePattern]
    default: Any
    callback: Optional[ConfigEntryCallback]
    required: bool


def prepare_default_config(meta_info_tree):

    def _prepare_default_config(_meta_info_tree):
        if isinstance(_meta_info_tree, ConfigEntryAttr):
            return deepcopy(_meta_info_tree.default)

        res = {}
        for key in _meta_info_tree:
            res[key] = _prepare_default_config(_meta_info_tree[key])
        return res

    return _prepare_default_config(meta_info_tree)


def check_config_integrity(meta_info_tree, config_tree, prefix=None):

    def _check_config_integrity(_meta_info_tree, _config_tree, _prefix=None):
        if isinstance(_meta_info_tree, ConfigEntryAttr):
            if _config_tree != ConfigEntryValueUnspecified:
                return True, None
            elif not _meta_info_tree.required:
                return True, [_prefix]
            else:
                return False, [_prefix]

        res = True
        res_list = []
        for key in _meta_info_tree:
            if _prefix is None:
                new_prefix = key
            else:
                new_prefix = _prefix + "." + key
            status, problem_list = _check_config_integrity(_meta_info_tree[key], _config_tree[key], new_prefix)
            if not status:
                res = False
                res_list.extend(problem_list)
        return res, res_list

    return _check_config_integrity(meta_info_tree, config_tree, prefix)


class ConfigRegistry:

    def __init__(self, prog: str = "prog", warn_unknown_key: bool = False):
        self.prog = prog
        self.warn_unknown_key = warn_unknown_key

        self.supported_seq_type: list[type] = [list, tuple]
        self.supported_map_type: list[type] = [dict]

        self.reset()

    def reset(self):
        # meta: store key info
        self.meta_info: dict[str, ConfigEntryAttr] = {}
        self.meta_info_tree: dict[str, Any] = {}
        self.category_proclist_cache: dict[Union[type, Any], Any] = {}

        # bind: store
        self.bind_config_filepath_list: list[str] = []

        # config: store parse res
        self.config = {}
        self.lack_key_list = []

    def reg_seq_type(self, newtype: type) -> None:
        if not isinstance(newtype, type):
            raise TypeError(f"Expected a type, got {type(newtype).__name__}: {newtype}")
        self.supported_seq_type.append(newtype)

    def reg_map_type(self, newtype: type) -> None:
        if not isinstance(newtype, type):
            raise TypeError(f"Expected a type, got {type(newtype).__name__}: {newtype}")
        self.supported_map_type.append(newtype)

    def register(
        self,
        key: str,
        prefix: Optional[str] = None,
        category: Union[type, Any] = Any,
        source: ConfigEntrySource = ConfigEntrySource.BUILTIN,
        desc: Optional[str] = None,
        required: bool = False,
        default: Any = ConfigEntryValueUnspecified,
        cmdpattern: Optional[ConfigEntryCommandlinePattern] = None,
        callback: Optional[ConfigEntryCallback] = None,
    ):
        # check key
        if key is None or len(key) == 0:
            return
        if key == "cfg":
            raise KeyError("collide with internal key!")

        # check cata
        if category != Any and not is_type(category):
            raise TypeError(f"error in category, got {category}")
        if category not in self.category_proclist_cache:
            proclist = analyze_type(category, self.supported_seq_type, self.supported_map_type)
            self.category_proclist_cache[category] = proclist

        # check src
        if not isinstance(source, ConfigEntrySource):
            raise TypeError(f"error in source, got {type(source)}")
        if source in [ConfigEntrySource.COMMANDLINE_ONLY, ConfigEntrySource.COMMANDLINE_OVER_CONFIG]:
            if not supported_by_commandline(self.category_proclist_cache[category]):
                raise TypeError(f"category not supported! got category {category}")
            if not proclist_pattern_paired(self.category_proclist_cache[category], cmdpattern, self.supported_seq_type,
                                           self.supported_map_type):
                raise TypeError(f"proclist & cmdpattern not paired! got category {category} and pattern {cmdpattern}")

        # key_list
        key_list = key.split(".")
        if prefix is not None:
            _key_list = prefix.split(".")
            key_list = _key_list + key_list
        internal_key = ".".join(key_list)

        # record
        attr_tuple = ConfigEntryAttr(
            source=source,
            desc=desc,
            category=category,
            cmdpattern=cmdpattern,
            default=default,
            callback=callback,
            required=required,
        )
        _handle = self.meta_info_tree
        for offset, key_part in enumerate(key_list):
            if key_part in _handle:
                if isinstance(_handle[key_part], ConfigEntryAttr):
                    raise KeyError(f"conflict prefix and key at {key_list[:offset+1]}")
                elif isinstance(_handle[key_part], dict) and offset == len(key_list) - 1:
                    raise KeyError(f"conflict prefix and key at {key_list[:offset+1]}")
                _handle = _handle[key_part]
            else:
                if offset == len(key_list) - 1:
                    _handle[key_part] = attr_tuple
                else:
                    _handle[key_part] = {}
                    _handle = _handle[key_part]
        self.meta_info[internal_key] = attr_tuple

        return self

    def bind_default_config_filepath(self, cfg_filepath: Union[str, Sequence[str]]):
        if isinstance(cfg_filepath, str):
            self.bind_config_filepath_list.append(cfg_filepath)
        else:
            self.bind_config_filepath_list.extend(cfg_filepath)

    def hook(self, parser: Optional[argparse.ArgumentParser] = None):
        if parser is None:
            return

        self.hook_config(parser)
        self.hook_arg(parser)

    def hook_config(self, parser: Optional[argparse.ArgumentParser] = None):
        # In segmented parsing, -c/--cfg is handled by split_argv_by_cfg() beforehand.
        # We still register a dummy option for:
        # 1. Displaying usage in --help
        # 2. Preventing users from registering conflicting -c/--cfg arguments
        if parser is None:
            return

        # Check if -c/--cfg already exists
        opt_str = list(parser._option_string_actions.keys())
        if "-c" in opt_str or "--cfg" in opt_str:
            raise KeyError("parser already have string action `-c` or `--cfg`!")

        # Register dummy option (actually handled by split_argv_by_cfg, never parsed by argparse)
        parser.add_argument(
            "-c",
            "--cfg",
            action="append",
            default=argparse.SUPPRESS,
            metavar="FILE",
            help=f"{self.__class__.__name__} config file (can be interleaved with options in any order)")

    def hook_arg(self, parser: Optional[argparse.ArgumentParser] = None):
        if parser is None:
            return

        # hook arg
        entry_cmdline = list(entry_key for entry_key, entry_meta in self.meta_info.items()
                             if entry_meta.source in (ConfigEntrySource.COMMANDLINE_ONLY,
                                                      ConfigEntrySource.COMMANDLINE_OVER_CONFIG))
        for entry_key in entry_cmdline:
            entry_meta = self.meta_info[entry_key]
            if entry_meta.category == bool:
                hook_cmd_bool(parser, entry_key, entry_meta.cmdpattern, entry_meta)
            else:
                # Add default=argparse.SUPPRESS so unprovided args don't appear in namespace
                parser.add_argument(f"--{entry_key}", default=argparse.SUPPRESS, help=entry_meta.desc)

    def _is_dict_type(self, entry_key: str) -> bool:
        """Check if a registered key has dict category."""
        if entry_key not in self.meta_info:
            return False
        entry_meta = self.meta_info[entry_key]
        proclist = self.category_proclist_cache.get(entry_meta.category)
        if proclist is None:
            return False
        return proclist["cast"] == "map"

    def _collect_leaf_keys(self, nested_dict: dict, prefix: str = "") -> list[str]:
        """
        Recursively collect all leaf keys from a nested dict as dot-notation strings.
        
        Stops recursion if the current key is registered as a dict type (its children
        are expected to be arbitrary and should not trigger unknown key warnings).
        """
        keys = []
        for k, v in nested_dict.items():
            full_key = f"{prefix}.{k}" if prefix else k
            # If this key is registered as dict type, don't recurse into its children
            if self._is_dict_type(full_key):
                keys.append(full_key)
            elif isinstance(v, dict):
                keys.extend(self._collect_leaf_keys(v, full_key))
            else:
                keys.append(full_key)
        return keys

    def _warn_unknown_keys(self, source_dict: dict, source_name: str) -> list[str]:
        """
        Warn about keys in source_dict that are not registered in meta_info.
        
        Returns the list of unknown keys (for testing purposes).
        """
        all_keys = self._collect_leaf_keys(source_dict)
        registered_keys = set(self.meta_info.keys())
        unknown_keys = [k for k in all_keys if k not in registered_keys]
        if unknown_keys:
            logger.warning(f"Unknown keys in {source_name} will be ignored: {unknown_keys}")
        return unknown_keys

    def _apply_config_file(self, config_tree, config_filepath, entry_config, warn_unknown_key: bool = False):
        """Load and apply a single config file."""
        config_ext = os.path.splitext(config_filepath)[1]
        if config_ext in [".yml", ".yaml"]:
            config_blob = load_yaml(config_filepath)
        else:
            raise RuntimeError(f"unsupported config type! got {repr(config_ext)}")

        # Warn about unknown keys if enabled
        if warn_unknown_key:
            self._warn_unknown_keys(config_blob, f"config file '{config_filepath}'")

        for entry_key in entry_config:
            entry_meta = self.meta_info[entry_key]
            index_status, raw_res = index_key(config_blob, entry_key)
            if index_status:
                cast_res = cast_to_res(raw_res, self.category_proclist_cache[entry_meta.category])
                set_value(config_tree, entry_key, cast_res)

    def _apply_cmdline_args(self, config_tree, parser, argv_segment):
        """Parse and apply a single command-line argument segment."""
        # Parse this segment
        namespace = parser.parse_args(argv_segment)
        parsed_dict = vars(namespace)  # Convert to dict

        # Only process explicitly provided args (due to SUPPRESS)
        entry_cmdline = list(entry_key for entry_key, entry_meta in self.meta_info.items()
                             if entry_meta.source in (ConfigEntrySource.COMMANDLINE_ONLY,
                                                      ConfigEntrySource.COMMANDLINE_OVER_CONFIG))

        for entry_key in entry_cmdline:
            entry_meta = self.meta_info[entry_key]

            # Handle boolean type
            if entry_meta.category == bool:
                raw_res = handle_cmd_bool(namespace, entry_key, entry_meta.cmdpattern)
                if raw_res == ConfigEntryValueUnspecified:
                    continue
            else:
                # Check if this arg was provided in this segment
                if entry_key not in parsed_dict:
                    continue

                raw_res = parsed_dict[entry_key]
                # Handle seq/map type cmdpattern
                if isinstance(entry_meta.cmdpattern, ConfigEntryCommandlineSeqPattern):
                    raw_res = handle_cmd_seq(raw_res, entry_meta.cmdpattern)
                elif isinstance(entry_meta.cmdpattern, ConfigEntryCommandlineMapPattern):
                    raw_res = handle_cmd_map(raw_res, entry_meta.cmdpattern)

            # Type cast and set value
            cast_res = cast_to_res(raw_res, self.category_proclist_cache[entry_meta.category])
            set_value(config_tree, entry_key, cast_res)

    def _apply_override(self, config_tree, cfg_override: dict, warn_unknown_key: bool = False):
        """
        Apply config overrides from a nested dict.
        
        Example: {"model": {"lr": 0.01, "batch_size": 32}}
        
        Only keys registered in meta_info are processed (consistent with _apply_config_file).
        """
        # Warn about unknown keys if enabled
        if warn_unknown_key:
            self._warn_unknown_keys(cfg_override, "cfg_override")

        for entry_key, entry_meta in self.meta_info.items():
            index_status, raw_value = index_key(cfg_override, entry_key)
            if index_status:
                cast_res = cast_to_res(raw_value, self.category_proclist_cache[entry_meta.category])
                set_value(config_tree, entry_key, cast_res)

    def _process_callbacks(self, config_tree):
        """Process all callbacks."""
        entry_callback_map = {}
        for entry_key, entry_meta in self.meta_info.items():
            if entry_meta.callback is not None and (entry_meta.callback.always or index_key(config_tree, entry_key)[1]
                                                    == ConfigEntryValueUnspecified):
                entry_callback_map[entry_key] = entry_meta.callback

        callback_run_order = resolve_callback_dependency(entry_callback_map)
        if callback_run_order is None:
            raise RuntimeError(f"circular dependency when solving callback order!")

        # process callback
        for entry_key in callback_run_order:
            entry_callback: ConfigEntryCallback = self.meta_info[entry_key].callback
            entry_value = index_key(config_tree, entry_key)[1]
            dep = {}
            for dep_key in entry_callback.dependency:
                dep[dep_key] = index_key(config_tree, dep_key)[1]
            callback_value = entry_callback(entry_key, entry_value, prog=self.prog, dep=dep)
            if callback_value != ConfigEntryValueUnspecified:
                set_value(config_tree, entry_key, callback_value)

    def _finalize_config(self, config_tree, strict):
        """Validate integrity and save config."""
        is_good, lack_key_list = check_config_integrity(self.meta_info_tree, config_tree)
        if strict and (not is_good):
            raise ValueError(f"unspecified value in config! key: {lack_key_list}")
        self.config = config_tree
        self.lack_key_list = lack_key_list

    def parse(self,
              parser: Optional[argparse.ArgumentParser] = None,
              arg_src=None,
              cfg_override=None,
              strict=True,
              warn_unknown_key: Optional[bool] = None):
        """
        Parse config files and command-line arguments in left-to-right order.

        :param parser: argparse.ArgumentParser
            parser to parse args from
        :param arg_src: list[str]
            arg list to parse
        :param cfg_override: dict
            config dict to override (nested format, e.g., {"model": {"lr": 0.01}})
        :param strict: bool
            if True, raise ValueError when required field has unspecified value in config
        :param warn_unknown_key: bool or None
            if True, log warning for unknown keys in config files and cfg_override;
            if None, use the instance attribute self.warn_unknown_key
        """
        # Resolve warn_unknown_key: per-call value overrides instance attribute
        _warn_unknown_key = self.warn_unknown_key if warn_unknown_key is None else warn_unknown_key

        # 1. Prepare default config
        _config = prepare_default_config(self.meta_info_tree)

        # 2. Get list of entries that can be read from config files
        entry_config = list(entry_key for entry_key, entry_meta in self.meta_info.items()
                            if entry_meta.source in (ConfigEntrySource.CONFIG_ONLY,
                                                     ConfigEntrySource.COMMANDLINE_OVER_CONFIG))

        # 3. Process pre-bound config files (bind_default_config_filepath)
        for config_filepath in self.bind_config_filepath_list:
            self._apply_config_file(_config, config_filepath, entry_config, warn_unknown_key=_warn_unknown_key)

        # 4. If no parser, skip command-line parsing
        if parser is None:
            # Still apply override if provided
            if cfg_override is not None:
                self._apply_override(_config, cfg_override, warn_unknown_key=_warn_unknown_key)
            self._process_callbacks(_config)
            self._finalize_config(_config, strict)
            return

        # 5. Segment-based argv processing
        if arg_src is None:
            arg_src = sys.argv[1:]

        segments = split_argv_by_cfg(arg_src)

        # 6. Process each segment in order
        for seg_type, seg_content in segments:
            if seg_type == 'cfg':
                # Load and apply config file
                self._apply_config_file(_config, seg_content, entry_config, warn_unknown_key=_warn_unknown_key)

            elif seg_type == 'args':
                # Parse and apply command-line arguments
                self._apply_cmdline_args(_config, parser, seg_content)

        # 7. Process override
        if cfg_override is not None:
            self._apply_override(_config, cfg_override, warn_unknown_key=_warn_unknown_key)

        # 8. Process callbacks
        self._process_callbacks(_config)

        # 9. Validate and save config
        self._finalize_config(_config, strict)

    def select(self, prefix: Optional[str] = None, strip=False):
        cfg = deepcopy(self.config)
        if strip:
            cfg = self.strip(cfg)
        if prefix is None:
            return cfg

        index_status, index_value = index_key(cfg, prefix)
        if not index_status:
            raise KeyError(f"prefix not found! got {prefix}")
        return index_value

    def strip(self, opt: Mapping):
        res = prepare_default_config(self.meta_info_tree)
        for entry_key in self.meta_info:
            index_status, index_value = index_key(opt, entry_key)
            if index_status and index_value != ConfigEntryValueUnspecified:
                set_value(res, entry_key, index_value)
            else:
                del_value(res, entry_key)
        return res

    def register_proxy(self, **kwarg):
        return RegisterProxy(self, **kwarg)


class RegisterProxy:

    def __init__(self, config_reg: ConfigRegistry, **kwarg) -> None:
        self.config_reg = config_reg
        self.kwarg = kwarg

    def register(self, *args, **kwargs):
        _kv = self.kwarg.copy()
        _kv.update(kwargs)
        self.config_reg.register(*args, **_kv)
        return self
