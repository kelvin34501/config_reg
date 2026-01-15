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
