import copy
import functools
from enum import Enum
from textwrap import dedent
from typing import Any, Callable, Dict, List, Sequence, Tuple, Union


class InstantiationException(Exception):
    pass


class _Keys(str, Enum):
    TARGET = "_target_"
    RECURSIVE = "_recursive_"
    ARGS = "_args_"
    PARTIAL = "_partial_"


def _is_target(x: Any) -> bool:
    return isinstance(x, dict) and "_target_" in x


def _extract_pos_args(input_args: Any, kwargs: Any) -> Tuple[Any, Any]:
    config_args = kwargs.pop(_Keys.ARGS, ())
    output_args = config_args
    if isinstance(config_args, Sequence):
        if len(input_args) > 0:
            output_args = input_args
    else:
        raise InstantiationException(f"Unsupported _args_ type: '{type(config_args).__name__}'. value: '{config_args}'")
    return output_args, kwargs


def _call_target(_target_: Callable[..., Any], _partial_: bool, args: Tuple[Any, ...], kwargs: Dict[str, Any],
                 full_key: str) -> Any:
    try:
        args, kwargs = _extract_pos_args(args, kwargs)
    except Exception as e:
        msg = f"Error in collecting args and kwargs for '{_convert_target_to_string(_target_)}': {repr(e)}"
        if full_key:
            msg += f"\nfull_key: {full_key}"
        raise InstantiationException(msg) from e

    if _partial_:
        try:
            return functools.partial(_target_, *args, **kwargs)
        except Exception as e:
            msg = f"Error in creating partial({_convert_target_to_string(_target_)}, ...) object: {repr(e)}"
            if full_key:
                msg += f"\nfull_key: {full_key}"
            raise InstantiationException(msg) from e
    else:
        try:
            return _target_(*args, **kwargs)
        except Exception as e:
            msg = f"Error in call to target '{_convert_target_to_string(_target_)}': {repr(e)}"
            if full_key:
                msg += f"\nfull_key: {full_key}"
            raise InstantiationException(msg) from e


def _convert_target_to_string(t: Any) -> Any:
    if callable(t):
        return f"{t.__module__}.{t.__qualname__}"
    else:
        return str(t)


def _prepare_input_dict_or_list(d: Union[Dict[Any, Any], List[Any]]) -> Any:
    res: Any
    if isinstance(d, dict):
        res = {}
        for k, v in d.items():
            if k == "_target_":
                v = _convert_target_to_string(d["_target_"])
            elif isinstance(v, (dict, list)):
                v = _prepare_input_dict_or_list(v)
            res[k] = v
    elif isinstance(d, list):
        res = []
        for v in d:
            if isinstance(v, (list, dict)):
                v = _prepare_input_dict_or_list(v)
            res.append(v)
    else:
        assert False
    return res


def _resolve_target(target: Union[str, type, Callable[..., Any]], full_key: str) -> Union[type, Callable[..., Any]]:
    """Resolve target string, type or callable into type or callable."""
    if isinstance(target, str):
        try:
            target = _locate(target)
        except Exception as e:
            msg = f"Error locating target '{target}'"
            if full_key:
                msg += f"\nfull_key: {full_key}"
            raise InstantiationException(msg) from e
    if not callable(target):
        msg = f"Expected a callable target, got '{target}' of type '{type(target).__name__}'"
        if full_key:
            msg += f"\nfull_key: {full_key}"
        raise InstantiationException(msg)
    return target


def _locate(path: str) -> Any:
    """
    Locate an object by name or dotted path, importing as necessary.
    This is similar to the pydoc function `locate`, except that it checks for
    the module from the given path from back to front.
    """
    if path == "":
        raise ImportError("Empty path")
    from importlib import import_module
    from types import ModuleType

    parts = [part for part in path.split(".")]
    for part in parts:
        if not len(part):
            raise ValueError(f"Error loading '{path}': invalid dotstring." + "\nRelative imports are not supported.")
    assert len(parts) > 0
    part0 = parts[0]
    try:
        obj = import_module(part0)
    except Exception as exc_import:
        raise ImportError(f"Error loading '{path}':\n{repr(exc_import)}" +
                          f"\nAre you sure that module '{part0}' is installed?") from exc_import
    for m in range(1, len(parts)):
        part = parts[m]
        try:
            obj = getattr(obj, part)
        except AttributeError as exc_attr:
            parent_dotpath = ".".join(parts[:m])
            if isinstance(obj, ModuleType):
                mod = ".".join(parts[:m + 1])
                try:
                    obj = import_module(mod)
                    continue
                except ModuleNotFoundError as exc_import:
                    raise ImportError(
                        f"Error loading '{path}':\n{repr(exc_import)}" +
                        f"\nAre you sure that '{part}' is importable from module '{parent_dotpath}'?") from exc_import
                except Exception as exc_import:
                    raise ImportError(f"Error loading '{path}':\n{repr(exc_import)}") from exc_import
            raise ImportError(f"Error loading '{path}':\n{repr(exc_attr)}" +
                              f"\nAre you sure that '{part}' is an attribute of '{parent_dotpath}'?") from exc_attr
    return obj


def instantiate_node(config: Any, *args: Any, recursive: bool = True, partial: bool = False, full_key: str="") -> Any:
    if config is None:
        return None
    
    if not isinstance(config, (list, dict)):
        return config

    if not isinstance(recursive, bool):
        msg = f"Instantiation: _recursive_ flag must be a bool, got {type(recursive)}"
        if full_key:
            msg += f"\nfull_key: {full_key}"
        raise TypeError(msg)

    if not isinstance(partial, bool):
        msg = f"Instantiation: _partial_ flag must be a bool, got {type( partial )}"
        if node and full_key:
            msg += f"\nfull_key: {full_key}"
        raise TypeError(msg)

    # main handling
    if isinstance(config, list):
        items = [instantiate_node(item, recursive=recursive) for item in config]
        return items

    elif isinstance(config, dict):
        exclude_keys = set({_Keys.TARGET, _Keys.RECURSIVE, _Keys.PARTIAL})
        if _is_target(config):
            _target_ = _resolve_target(config.get(_Keys.TARGET, ""), full_key)
            kwargs = {}
            for key in config.keys():
                if key not in exclude_keys:
                    value = config[key]
                    if recursive:
                        value = instantiate_node(value, recursive=recursive)
                    kwargs[key] = value
            return _call_target(_target_, partial, args, kwargs, full_key)

        else:
            return {k: instantiate_node(v, recursive=recursive) for k, v in config.items()}

    else:
        raise InstantiationException(f"Unexpected config type: {type(config).__name__}")


def instantiate(config: Union[Dict[Any, Any], List[Any]], *args: Any, full_key: str = "", **kwargs: Any) -> Any:
    if config is None:
        return None

    if "_target_" not in config or config["_target_"] is None or config["_target_"] == "":
        raise InstantiationException(
            dedent("""\
            Config has missing value for key `_target_`, cannot instantiate.
            Config type: {type(config).__name__}
            Check that the `_target_` key in your dataclass is properly annotated and overridden.
        """))

    if isinstance(config, (dict, list)):
        config = _prepare_input_dict_or_list(config)
    kwargs = _prepare_input_dict_or_list(kwargs)

    if isinstance(config, dict):
        config_copy = copy.deepcopy(config)
        if kwargs:
            config_copy.update(kwargs)

        _recursive_ = config_copy.pop(_Keys.RECURSIVE, True)
        _partial_ = config_copy.pop(_Keys.PARTIAL, False)

        return instantiate_node(
            config_copy,
            *args,
            recursive=_recursive_,
            partial=_partial_,
            full_key=full_key,
        )

    elif isinstance(config, list):
        config_copy = copy.deepcopy(config)
        return instantiate_node(
            config_copy,
            *args,
            recursive=kwargs.pop(_Keys.RECURSIVE, True),
            partial=kwargs.pop(_Keys.PARTIAL, False),
            full_key=full_key,
        )

    else:
        raise InstantiationException(
            dedent(f"""\
            Cannot instantiate config of type {type(config).__name__}.
            Top level config must be a plain dict/list, or a structured config class or instance."""))
