"""Tests for instantiate functionality in convert.py"""

import functools
import pytest
from config_reg.convert import instantiate, instantiate_node, InstantiationException


# Test helper classes
class SimpleClass:

    def __init__(self, value):
        self.value = value


class ParentClass:

    def __init__(self, child, name="parent"):
        self.child = child
        self.name = name


class ChildClass:

    def __init__(self, data):
        self.data = data


class GrandchildClass:

    def __init__(self, id):
        self.id = id


# =============================================================================
# Basic Instantiation Tests
# =============================================================================


class TestBasicInstantiation:

    def test_simple_instantiation(self):
        """Test basic instantiation with _target_"""
        config = {"_target_": "test.test_instantiate.SimpleClass", "value": 42}
        result = instantiate(config)
        assert isinstance(result, SimpleClass)
        assert result.value == 42

    def test_instantiation_with_callable_target(self):
        """Test instantiation with callable (not string) as _target_"""
        config = {"_target_": SimpleClass, "value": "hello"}
        result = instantiate(config)
        assert isinstance(result, SimpleClass)
        assert result.value == "hello"

    def test_nested_instantiation(self):
        """Test recursive instantiation of nested configs"""
        config = {
            "_target_": "test.test_instantiate.ParentClass",
            "child": {
                "_target_": "test.test_instantiate.ChildClass",
                "data": {
                    "key": "value"
                }
            },
            "name": "test_parent"
        }
        result = instantiate(config)
        assert isinstance(result, ParentClass)
        assert isinstance(result.child, ChildClass)
        assert result.child.data == {"key": "value"}

    def test_none_config_returns_none(self):
        """Test that None config returns None"""
        result = instantiate_node(None)
        assert result is None

    def test_primitive_config_returns_as_is(self):
        """Test that primitives pass through unchanged"""
        assert instantiate_node(42) == 42
        assert instantiate_node("hello") == "hello"
        assert instantiate_node(3.14) == 3.14


# =============================================================================
# Node-Level _recursive_ Override Tests
# =============================================================================


class TestNodeLevelRecursive:

    def test_top_level_recursive_false(self):
        """Test _recursive_: false at top level stops all recursion"""
        config = {
            "_target_": "test.test_instantiate.ParentClass",
            "_recursive_": False,
            "child": {
                "_target_": "test.test_instantiate.ChildClass",
                "data": "test"
            },
            "name": "parent"
        }
        result = instantiate(config)
        assert isinstance(result, ParentClass)
        # child should remain as dict, not instantiated
        assert isinstance(result.child, dict)
        assert result.child["_target_"] == "test.test_instantiate.ChildClass"

    def test_node_level_recursive_false_stops_children(self):
        """Test _recursive_: false at node level stops that node's children only"""
        config = {
            "_target_": "test.test_instantiate.ParentClass",
            "_recursive_": True,  # top level recursive
            "child": {
                "_target_": "test.test_instantiate.ParentClass",
                "_recursive_": False,  # stop recursion here
                "child": {
                    "_target_": "test.test_instantiate.ChildClass",
                    "data": "should_be_dict"
                },
                "name": "middle"
            },
            "name": "top"
        }
        result = instantiate(config)

        # Top level instantiated
        assert isinstance(result, ParentClass)
        assert result.name == "top"

        # Middle level instantiated (because parent's _recursive_ is True)
        assert isinstance(result.child, ParentClass)
        assert result.child.name == "middle"

        # Grandchild should remain as dict (because middle's _recursive_ is False)
        assert isinstance(result.child.child, dict)
        assert result.child.child["_target_"] == "test.test_instantiate.ChildClass"

    def test_deep_nested_recursive_override(self):
        """Test _recursive_ override at multiple levels"""
        config = {
            "_target_": "test.test_instantiate.ParentClass",
            "child": {
                "_target_": "test.test_instantiate.ParentClass",
                "_recursive_": False,  # stop here
                "child": {
                    "_target_": "test.test_instantiate.ParentClass",
                    "_recursive_": True,  # this won't matter, parent stopped
                    "child": {
                        "_target_": "test.test_instantiate.ChildClass",
                        "data": "deep"
                    }
                }
            }
        }
        result = instantiate(config)

        assert isinstance(result, ParentClass)
        assert isinstance(result.child, ParentClass)
        # The third level should be dict because middle set _recursive_: False
        assert isinstance(result.child.child, dict)


# =============================================================================
# Node-Level _partial_ Override Tests
# =============================================================================


class TestNodeLevelPartial:

    def test_top_level_partial(self):
        """Test _partial_: true creates functools.partial"""
        config = {"_target_": "test.test_instantiate.SimpleClass", "_partial_": True, "value": 100}
        result = instantiate(config)
        assert isinstance(result, functools.partial)
        # Call the partial to get the actual instance
        instance = result()
        assert isinstance(instance, SimpleClass)
        assert instance.value == 100

    def test_node_level_partial_override(self):
        """Test _partial_ at node level creates partial for that node only"""
        config = {
            "_target_": "test.test_instantiate.ParentClass",
            "_partial_": False,  # top level fully instantiated
            "child": {
                "_target_": "test.test_instantiate.SimpleClass",
                "_partial_": True,  # child should be partial
                "value": 50
            },
            "name": "parent"
        }
        result = instantiate(config)

        # Parent fully instantiated
        assert isinstance(result, ParentClass)
        # Child should be a partial
        assert isinstance(result.child, functools.partial)
        # Calling the partial creates the instance
        child_instance = result.child()
        assert isinstance(child_instance, SimpleClass)
        assert child_instance.value == 50


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:

    def test_missing_target_raises(self):
        """Test that missing _target_ raises InstantiationException"""
        config = {"value": 42}
        with pytest.raises(InstantiationException):
            instantiate(config)

    def test_empty_target_raises(self):
        """Test that empty _target_ raises InstantiationException"""
        config = {"_target_": "", "value": 42}
        with pytest.raises(InstantiationException):
            instantiate(config)

    def test_none_target_raises(self):
        """Test that None _target_ raises InstantiationException"""
        config = {"_target_": None, "value": 42}
        with pytest.raises(InstantiationException):
            instantiate(config)

    def test_invalid_target_path_raises(self):
        """Test that invalid target path raises InstantiationException"""
        config = {"_target_": "nonexistent.module.Class", "value": 42}
        with pytest.raises(InstantiationException):
            instantiate(config)

    def test_invalid_recursive_type_raises(self):
        """Test that non-bool _recursive_ raises TypeError"""
        config = {
            "_target_": "test.test_instantiate.SimpleClass",
            "_recursive_": "yes",  # should be bool
            "value": 42
        }
        with pytest.raises(TypeError):
            instantiate(config)

    def test_invalid_partial_type_raises(self):
        """Test that non-bool _partial_ raises TypeError"""
        config = {
            "_target_": "test.test_instantiate.SimpleClass",
            "_partial_": 1,  # should be bool
            "value": 42
        }
        with pytest.raises(TypeError):
            instantiate(config)


# =============================================================================
# List Config Tests
# =============================================================================


class TestListConfig:

    def test_list_of_targets(self):
        """Test instantiation of list containing target configs"""
        config = {
            "_target_": "test.test_instantiate.ParentClass",
            "child": [
                {
                    "_target_": "test.test_instantiate.SimpleClass",
                    "value": 1
                },
                {
                    "_target_": "test.test_instantiate.SimpleClass",
                    "value": 2
                },
            ],
            "name": "list_parent"
        }
        result = instantiate(config)
        assert isinstance(result, ParentClass)
        assert isinstance(result.child, list)
        assert len(result.child) == 2
        assert all(isinstance(c, SimpleClass) for c in result.child)
        assert result.child[0].value == 1
        assert result.child[1].value == 2


# =============================================================================
# _args_ Tests
# =============================================================================


class TestPositionalArgs:

    def test_args_in_config(self):
        """Test _args_ for positional arguments"""
        config = {"_target_": "test.test_instantiate.SimpleClass", "_args_": ["positional_value"]}
        result = instantiate(config)
        assert isinstance(result, SimpleClass)
        assert result.value == "positional_value"


# =============================================================================
# Dataclass Config Tests
# =============================================================================

from dataclasses import dataclass, field


# Dataclass test helper classes
@dataclass
class SimpleDataclassConfig:
    _target_: str = "test.test_instantiate.SimpleClass"
    value: int = 42


@dataclass
class ChildDataclassConfig:
    _target_: str = "test.test_instantiate.ChildClass"
    data: str = "default_data"


@dataclass
class ParentDataclassConfig:
    _target_: str = "test.test_instantiate.ParentClass"
    child: ChildDataclassConfig = field(default_factory=ChildDataclassConfig)
    name: str = "dataclass_parent"


@dataclass
class RecursiveFalseParentConfig:
    _target_: str = "test.test_instantiate.ParentClass"
    _recursive_: bool = False
    child: ChildDataclassConfig = field(default_factory=ChildDataclassConfig)
    name: str = "non_recursive_parent"


@dataclass
class PartialChildConfig:
    _target_: str = "test.test_instantiate.SimpleClass"
    _partial_: bool = True
    value: int = 100


@dataclass
class ParentWithPartialChildConfig:
    _target_: str = "test.test_instantiate.ParentClass"
    child: PartialChildConfig = field(default_factory=PartialChildConfig)
    name: str = "parent_with_partial"


@dataclass
class CallableTargetConfig:
    _target_: type = SimpleClass  # Callable, not string
    value: str = "callable_target"


class DerivedValueClass:
    """Helper class that accepts base_value, multiplier, and value"""
    def __init__(self, base_value, multiplier, value):
        self.base_value = base_value
        self.multiplier = multiplier
        self.value = value


@dataclass
class DerivedFieldConfig:
    """Config where value is derived from other fields via __post_init__"""
    _target_: str = "test.test_instantiate.DerivedValueClass"
    base_value: int = 10
    multiplier: int = 5
    value: int = field(init=False)  # Derived field - will be computed

    def __post_init__(self):
        self.value = self.base_value * self.multiplier


@dataclass
class GrandchildDataclassConfig:
    _target_: str = "test.test_instantiate.GrandchildClass"
    id: int = 1


@dataclass
class MiddleDataclassConfig:
    _target_: str = "test.test_instantiate.ChildClass"
    _recursive_: bool = False  # Stop recursion here
    data: GrandchildDataclassConfig = field(default_factory=GrandchildDataclassConfig)


@dataclass
class TopDataclassConfig:
    _target_: str = "test.test_instantiate.ParentClass"
    child: MiddleDataclassConfig = field(default_factory=MiddleDataclassConfig)
    name: str = "top"


class TestDataclassConfig:

    def test_simple_dataclass(self):
        """Test basic dataclass config instantiation"""
        cfg = SimpleDataclassConfig(value=100)
        result = instantiate(cfg)
        assert isinstance(result, SimpleClass)
        assert result.value == 100

    def test_nested_dataclass(self):
        """Test nested dataclass configs are recursively instantiated"""
        cfg = ParentDataclassConfig(
            child=ChildDataclassConfig(data="nested_value"),
            name="test_parent"
        )
        result = instantiate(cfg)
        assert isinstance(result, ParentClass)
        assert isinstance(result.child, ChildClass)
        assert result.child.data == "nested_value"
        assert result.name == "test_parent"

    def test_dataclass_recursive_false_stops_children(self):
        """Test _recursive_: False in dataclass stops child instantiation"""
        cfg = RecursiveFalseParentConfig(
            child=ChildDataclassConfig(data="should_be_dict")
        )
        result = instantiate(cfg)
        assert isinstance(result, ParentClass)
        # child should remain as dict, not instantiated
        assert isinstance(result.child, dict)
        assert result.child["_target_"] == "test.test_instantiate.ChildClass"
        assert result.child["data"] == "should_be_dict"

    def test_dataclass_node_level_recursive_false(self):
        """Test node-level _recursive_: False in nested dataclass"""
        cfg = TopDataclassConfig()
        result = instantiate(cfg)
        
        # Top level instantiated
        assert isinstance(result, ParentClass)
        assert result.name == "top"
        
        # Middle level instantiated (top's _recursive_ is True by default)
        assert isinstance(result.child, ChildClass)
        
        # Grandchild should be dict (middle's _recursive_ is False)
        assert isinstance(result.child.data, dict)
        assert result.child.data["_target_"] == "test.test_instantiate.GrandchildClass"

    def test_dataclass_partial_child(self):
        """Test _partial_: True in nested dataclass creates functools.partial"""
        cfg = ParentWithPartialChildConfig()
        result = instantiate(cfg)
        
        assert isinstance(result, ParentClass)
        # child should be a partial
        assert isinstance(result.child, functools.partial)
        # Calling the partial creates the instance
        child_instance = result.child()
        assert isinstance(child_instance, SimpleClass)
        assert child_instance.value == 100

    def test_dataclass_callable_target(self):
        """Test dataclass with callable (type) as _target_"""
        cfg = CallableTargetConfig(value="test_callable")
        result = instantiate(cfg)
        assert isinstance(result, SimpleClass)
        assert result.value == "test_callable"

    def test_dataclass_derived_field(self):
        """Test dataclass with derived field (init=False) via __post_init__"""
        cfg = DerivedFieldConfig(base_value=20, multiplier=3)
        # value should be 20 * 3 = 60
        assert cfg.value == 60
        result = instantiate(cfg)
        assert isinstance(result, DerivedValueClass)
        # The derived value should be passed to target
        assert result.value == 60
        assert result.base_value == 20
        assert result.multiplier == 3
        assert result.value == 60

    def test_dataclass_mixed_with_dict(self):
        """Test dataclass containing dict children"""
        @dataclass
        class MixedConfig:
            _target_: str = "test.test_instantiate.ParentClass"
            child: dict = field(default_factory=lambda: {
                "_target_": "test.test_instantiate.ChildClass",
                "data": "from_dict"
            })
            name: str = "mixed"

        cfg = MixedConfig()
        result = instantiate(cfg)
        assert isinstance(result, ParentClass)
        assert isinstance(result.child, ChildClass)
        assert result.child.data == "from_dict"

    def test_dict_containing_dataclass(self):
        """Test dict config containing dataclass children"""
        config = {
            "_target_": "test.test_instantiate.ParentClass",
            "child": ChildDataclassConfig(data="dataclass_in_dict"),
            "name": "dict_parent"
        }
        result = instantiate(config)
        assert isinstance(result, ParentClass)
        assert isinstance(result.child, ChildClass)
        assert result.child.data == "dataclass_in_dict"

    def test_dataclass_list_children(self):
        """Test dataclass with list of dataclass children"""
        @dataclass
        class ListChildrenConfig:
            _target_: str = "test.test_instantiate.ParentClass"
            child: list = field(default_factory=lambda: [
                SimpleDataclassConfig(value=1),
                SimpleDataclassConfig(value=2),
            ])
            name: str = "list_parent"

        cfg = ListChildrenConfig()
        result = instantiate(cfg)
        assert isinstance(result, ParentClass)
        assert isinstance(result.child, list)
        assert len(result.child) == 2
        assert all(isinstance(c, SimpleClass) for c in result.child)
        assert result.child[0].value == 1
        assert result.child[1].value == 2

    def test_dataclass_default_values(self):
        """Test dataclass with default values"""
        cfg = SimpleDataclassConfig()  # Use all defaults
        result = instantiate(cfg)
        assert isinstance(result, SimpleClass)
        assert result.value == 42  # default value

    def test_dataclass_deep_nesting(self):
        """Test deeply nested dataclass configs"""
        @dataclass
        class Level3Config:
            _target_: str = "test.test_instantiate.GrandchildClass"
            id: int = 3

        @dataclass
        class Level2Config:
            _target_: str = "test.test_instantiate.ChildClass"
            data: Level3Config = field(default_factory=Level3Config)

        @dataclass
        class Level1Config:
            _target_: str = "test.test_instantiate.ParentClass"
            child: Level2Config = field(default_factory=Level2Config)
            name: str = "level1"

        cfg = Level1Config()
        result = instantiate(cfg)
        
        assert isinstance(result, ParentClass)
        assert isinstance(result.child, ChildClass)
        assert isinstance(result.child.data, GrandchildClass)
        assert result.child.data.id == 3
