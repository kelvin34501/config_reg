import os
import argparse
from typing import Optional, Union, Any
from typing import Sequence
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

from .callback import ConfigEntryCallback, resolve_callback_dependency

from .if_yaml import load_yaml

from copy import deepcopy


@dataclass
class ConfigEntryAttr:
    source: ConfigEntrySource
    desc: Optional[str]
    category: Union[type, Any]
    cmdpattern: Optional[ConfigEntryCommandlinePattern]
    default: Any
    callback: Optional[ConfigEntryCallback]


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
    def __init__(self, prog: str = "prog"):
        self.prog = prog

        self.supported_seq_type: list[type] = [list, tuple]
        self.supported_map_type: list[type] = [dict]

        self.reset()

    def reset(self):
        # meta: store key info
        self.meta_info: dict[str, ConfigEntryAttr] = {}
        self.meta_info_tree: dict[str, Any] = {}
        self.category_proclist_cache: dict[Union[type, Any], Any] = {}

        # bind: store
        self.bind_config_list: list[str] = []

        # config: store parse res
        self.config = {}

    def reg_seq_type(self, newtype: type):
        assert isinstance(newtype, type)
        self.supported_seq_type.append(newtype)

    def reg_map_type(self, newtype: type):
        assert isinstance(newtype, type)
        self.supported_map_type.append(newtype)

    def register(
        self,
        key: str,
        prefix: Optional[str] = None,
        category: Union[type, Any] = Any,
        source: ConfigEntrySource = ConfigEntrySource.BUILTIN,
        desc: Optional[str] = None,
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
        if category != Any and not isinstance(category, type):
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
            if not proclist_pattern_paired(
                self.category_proclist_cache[category], cmdpattern, self.supported_seq_type, self.supported_map_type
            ):
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

    def bind_default_config(self, cfg: Union[str, Sequence[str]]):
        if isinstance(cfg, Sequence):
            self.bind_config_list.extend(cfg)
        else:
            self.bind_config_list.append(cfg)

    def hook(self, parser: Optional[argparse.ArgumentParser] = None):
        if parser is None:
            return

        self.hook_config(parser)
        self.hook_arg(parser)

    def hook_config(self, parser: Optional[argparse.ArgumentParser] = None):
        if parser is None:
            return

        # check if parser has "-c,--cfg" field
        opt_str = list(parser._option_string_actions.keys())
        if "-c" in opt_str or "--cfg" in opt_str:
            raise KeyError("parser already have string action `-c` or `--cfg`!")

        # append config args
        parser.add_argument("-c", "--cfg", action="append", help=f"{self.__class__.__name__} config file")

    def hook_arg(self, parser: Optional[argparse.ArgumentParser] = None):
        if parser is None:
            return

        # hook arg
        entry_cmdline = list(
            entry_key
            for entry_key, entry_meta in self.meta_info.items()
            if entry_meta.source in (ConfigEntrySource.COMMANDLINE_ONLY, ConfigEntrySource.COMMANDLINE_OVER_CONFIG)
        )
        for entry_key in entry_cmdline:
            entry_meta = self.meta_info[entry_key]
            if entry_meta.category == bool:
                hook_cmd_bool(parser, entry_key, entry_meta.cmdpattern, entry_meta)
            else:
                parser.add_argument(f"--{entry_key}", help=entry_meta.desc)

    def parse(self, parser: Optional[argparse.ArgumentParser] = None, arg_src=None, cfg_override=None):
        # get a copy of default arg
        # required arg is leave to sentry
        _config = prepare_default_config(self.meta_info_tree)

        if parser is None:
            parse_res = None
        else:
            # parse arg for cfg
            parse_res = parser.parse_args(arg_src)

            cfg_list = getattr(parse_res, "cfg", None)
            if cfg_list is not None:
                self.bind_config_list.extend(cfg_list)

        # process cfg
        entry_config = list(
            entry_key
            for entry_key, entry_meta in self.meta_info.items()
            if entry_meta.source in (ConfigEntrySource.CONFIG_ONLY, ConfigEntrySource.COMMANDLINE_OVER_CONFIG)
        )
        for config_filepath in self.bind_config_list:
            config_ext = os.path.splitext(config_filepath)[1]
            if config_ext in [".yml", ".yaml"]:
                config_blob = load_yaml(config_filepath)
            else:
                raise RuntimeError(f"unsupported config type! got {repr(config_ext)}")

            for entry_key in entry_config:
                entry_meta = self.meta_info[entry_key]
                index_status, raw_res = index_key(config_blob, entry_key)
                if index_status:
                    cast_res = cast_to_res(raw_res, self.category_proclist_cache[entry_meta.category])
                    set_value(_config, entry_key, cast_res)

        # process command line
        if parse_res is None:
            pass
        else:
            # override with arg
            entry_cmdline = list(
                entry_key
                for entry_key, entry_meta in self.meta_info.items()
                if entry_meta.source in (ConfigEntrySource.COMMANDLINE_ONLY, ConfigEntrySource.COMMANDLINE_OVER_CONFIG)
            )
            for entry_key in entry_cmdline:
                entry_meta = self.meta_info[entry_key]
                if entry_meta.category == bool:
                    raw_res = handle_cmd_bool(parse_res, entry_key, entry_meta.cmdpattern)
                    if raw_res == ConfigEntryValueUnspecified:
                        continue
                else:
                    raw_res = getattr(parse_res, entry_key)
                    if raw_res is None:
                        continue
                    # handle raw_res
                    if isinstance(entry_meta.cmdpattern, ConfigEntryCommandlineSeqPattern):
                        raw_res = handle_cmd_seq(raw_res, entry_meta.cmdpattern)
                    elif isinstance(entry_meta.cmdpattern, ConfigEntryCommandlineMapPattern):
                        raw_res = handle_cmd_map(raw_res, entry_meta.cmdpattern)
                cast_res = cast_to_res(raw_res, self.category_proclist_cache[entry_meta.category])
                set_value(_config, entry_key, cast_res)

        # TODO: process override
        pass

        # * experimental: resolve callback dependency
        entry_callback_map = {}
        for entry_key, entry_meta in self.meta_info.items():
            if entry_meta.callback is not None and (
                entry_meta.callback.always or index_key(_config, entry_key)[1] == ConfigEntryValueUnspecified
            ):
                entry_callback_map[entry_key] = entry_meta.callback
        callback_run_order = resolve_callback_dependency(entry_callback_map)
        if callback_run_order is None:
            raise RuntimeError(f"circular dependency when solving callback order!")

        # process callback
        for entry_key in callback_run_order:
            entry_callback: ConfigEntryCallback = self.meta_info[entry_key].callback
            entry_value = index_key(_config, entry_key)[1]
            dep = {}
            for dep_key in entry_callback.dependency:
                dep[dep_key] = index_key(_config, dep_key)[1]
            callback_value = entry_callback(entry_key, entry_value, prog=self.prog, dep=dep)
            if callback_value != ConfigEntryValueUnspecified:
                set_value(_config, entry_key, callback_value)

        # self.config bind to new config
        # return default arg
        is_good, lack_key_list = check_config_integrity(self.meta_info_tree, _config)
        if not is_good:
            raise ValueError(f"unspecified value in config! key: {lack_key_list}")
        self.config = _config

    def select(self, prefix: Optional[str] = None):
        if prefix is None:
            return deepcopy(self.config)

        index_status, index_value = index_key(self.config, prefix)
        if not index_status:
            raise KeyError(f"prefix not found! got {prefix}")
        return deepcopy(index_value)


def set_value(config, key, value):
    key_list = key.split(".")
    handle = config
    for keypart in key_list[:-1]:
        handle = handle[keypart]
    handle[key_list[-1]] = value


def index_key(tree, key):
    if tree is None:
        return False, None

    key_list = key.split(".")
    handle = tree
    for keypart in key_list:
        if keypart not in handle:
            return False, None
        handle = handle[keypart]
    return True, handle
