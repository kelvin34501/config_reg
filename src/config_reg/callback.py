from __future__ import annotations

import os
import typing

from .type_def import ConfigEntryValueUnspecified


class ConfigEntryCallback:
    dependency: list[str] = []
    always: bool = False

    def __call__(self, curr_key: str, curr_value: typing.Any, prog: str, dep: typing.Mapping) -> typing.Any:
        return ConfigEntryValueUnspecified


def resolve_callback_dependency(callback_map: typing.Mapping[str, ConfigEntryCallback]) -> typing.Optional[list[str]]:
    """Resolve callback dependencies using topological sort.
    
    Args:
        callback_map: Mapping of key names to their callback objects.
        
    Returns:
        A list of keys in topologically sorted order (dependencies first),
        or None if there is a cyclic dependency.
    """
    # obtain adj list
    all_keys = set(callback_map.keys())
    adj_list: dict[str, list[str]] = {}
    for k, v in callback_map.items():
        dlist = []
        for d in v.dependency:
            if d in all_keys:
                dlist.append(d)
        adj_list[k] = dlist

    # get proc requirement
    proc_dep_list = adj_list.copy()
    proc_clear_list: dict[str, list[str]] = {}
    for k, dlist in proc_dep_list.items():
        for vv in dlist:
            if vv not in proc_clear_list:
                proc_clear_list[vv] = []
            proc_clear_list[vv].append(k)

    # toposort
    res = []
    while True:
        if len(proc_dep_list) == 0:
            break

        # iterate over proc_dep_list to find whether have a 0
        k_curr = next(iter(proc_dep_list.keys()))
        indeg_curr = len(proc_dep_list[k_curr])
        for _k in proc_dep_list:
            _indeg = len(proc_dep_list[_k])
            if _indeg < indeg_curr:
                k_curr = _k
                indeg_curr = _indeg
                if indeg_curr == 0:
                    break

        if indeg_curr > 0:
            return None

        res.append(k_curr)

        if k_curr in proc_clear_list:
            clear_list = proc_clear_list[k_curr]
            for k_node in clear_list:
                proc_dep_list[k_node].remove(k_curr)
            proc_clear_list.pop(k_curr)

        proc_dep_list.pop(k_curr)
    return res


# common callbacks
class AbspathCallback(ConfigEntryCallback):
    always: bool = True

    def __init__(self) -> None:
        super().__init__()
        self.curr_path = os.getcwd()

    def to_abs(self, v):
        if os.path.isabs(v):
            return os.path.normcase(os.path.normpath(v))
        else:
            return os.path.normcase(os.path.normpath(os.path.join(self.curr_path, v)))

    def __call__(self, curr_key: str, curr_value: typing.Any, prog: str, dep: typing.Mapping) -> typing.Any:
        if curr_value == ConfigEntryValueUnspecified or curr_value is None:
            return curr_value

        if isinstance(curr_value, list):
            return [self.to_abs(e) for e in curr_value]
        else:
            return self.to_abs(curr_value)


abspath_callback = AbspathCallback()


class InterpolationCallback(ConfigEntryCallback):
    always: bool = False

    def __init__(self, template: str, ensure_str=True) -> None:
        super().__init__()

        from .util import subst_util

        self.template = template
        self.ensure_str = ensure_str

        # extract dependency
        key_list, span_list = subst_util.extract_special_part(self.template)
        self.key_list = key_list
        self.span_list = span_list
        self.dependency = self.key_list.copy()

    def __call__(self, curr_key: str, curr_value: typing.Any, prog: str, dep: typing.Mapping) -> typing.Any:
        from .util import subst_util
        from .index import index_key
        if curr_key in self.key_list:
            raise ValueError(f"Cyclic dependency detected: key '{curr_key}' references itself in template")

        replacement_list = []
        for k in self.key_list:
            if k not in dep:
                raise KeyError(f"Key '{k}' not found in dependency, got dep keys: {list(dep.keys())}")
            v = dep[k]
            if self.ensure_str:
                if not isinstance(v, str):
                    raise TypeError(f"Expected str value for key '{k}', got {type(v).__name__}: {v}")
            replacement_list.append(str(v))

        new_value = subst_util.replace_from_span(self.template, self.span_list, replacement_list)
        return new_value
