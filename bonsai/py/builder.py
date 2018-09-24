# Copyright (c) 2018 Davide Laezza
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

###############################################################################
# Imports
###############################################################################

import ast
import re

import bonsai.model as bonsai_model
import bonsai.py.model as py_model

from bonsai.py import operator_names

###############################################################################
# Functions
###############################################################################


def identity(x):
    return x


###############################################################################
# Builder
###############################################################################


class PyBonsaiBuilder(object):
    """

    Holds a scope and a parent and builds children into results


    """

    and_name = operator_names[ast.And]
    bonsai_prefix = re.compile('^Code')

    @classmethod
    def _expand_compare(cls, scope, parent, args):
        is_only_arg = len(args) == 1

        and_node = py_model.PyOperator(scope, parent, cls.and_name,
                                       from_compare=True)
        parent = parent if is_only_arg else and_node

        left, op, right = args[0]
        left_node = py_model.PyOperator(scope, parent, op, from_compare=True)
        left_node._add(left)
        left_node._add(right)

        cls._set_parent_and_scope(left, scope, left_node)
        cls._set_parent_and_scope(right, scope, left_node)

        if is_only_arg:
            return left_node

        right_node = cls._expand_compare(scope, parent, args[1:])

        and_node._add(left_node)
        and_node._add(right_node)

        return and_node

    @classmethod
    def _make_class_name(cls, bonsai_node):
        return re.sub(cls.bonsai_prefix, 'Py', bonsai_node.__class__.__name__)

    @staticmethod
    def _set_parent_and_scope(bonsai_node, scope, parent):
        if isinstance(bonsai_node, bonsai_model.CodeEntity):
            setattr(bonsai_node, 'scope', scope)
            setattr(bonsai_node, 'parent', parent)

    def _make_key_value(self, pair):
        key, value = pair
        key_val = py_model.PyKeyValue(self.scope, self.parent, key, value)

        self._set_parent_and_scope(key, key_val.scope, key_val)
        self._set_parent_and_scope(value, key_val.scope, key_val)

        return key_val

    def __init__(self, parent=None, scope=None, props=None):
        self.children = []

        self.parent = parent
        self.scope = scope or parent
        self.props = props or {}

    def __getattr__(self, item):
        try:
            return self.props[item]
        except KeyError:
            raise AttributeError()

    def add_child(self, child):
        self.children.append(child)
        return self

    def finalize(self, bonsai_node):
        method_name = 'finalize_' + self._make_class_name(bonsai_node)
        return getattr(self, method_name, identity)(bonsai_node)

    def finalize_PyCompositeLiteral(self, bonsai_node):
        if bonsai_node.result == 'dict':
            half = len(self.children) // 2
            pairs = zip(self.children[:half], self.children[half:])
            children = map(self._make_key_value, pairs)
        else:
            children = self.children

        for value in children:
            bonsai_node._add_value(value)
        return bonsai_node

    def finalize_PyComprehension(self, bonsai_node):
        if 'dict' in bonsai_node.name:
            key, value = self.children[:2]
            key_value = py_model.PyKeyValue(bonsai_node, bonsai_node, key,
                                            value)
            self._set_parent_and_scope(key, key_value.scope, key_value)
            self._set_parent_and_scope(value, key_value.scope, key_value)
            bonsai_node.expr = key_value
            first_iter_index = 2
        else:
            bonsai_node.expr = self.children[0]
            first_iter_index = 1

        bonsai_node.iters = self.children[first_iter_index:]
        return bonsai_node

    def finalize_PyComprehensionIterator(self, bonsai_node):
        bonsai_node.target = self.children[0]
        bonsai_node.iter = self.children[1]
        bonsai_node.filters = tuple(self.children[2:])
        return bonsai_node

    def finalize_PyExpressionStatement(self, bonsai_node):
        bonsai_node.expression = self.children[0]
        return bonsai_node

    def finalize_PyFunctionCall(self, bonsai_node):
        function_name = self.children[0]
        bonsai_node.name = function_name.name
        if function_name.field_of is not None:
            bonsai_node._set_method(function_name.field_of)

        start, end = 1, 1 + self.args_count
        for arg in self.children[start:end]:
            bonsai_node._add(arg)

        start, end = end, end + self.kwargs_count
        bonsai_node.named_args = tuple(self.children[start:end])

        if self.has_starargs:
            start, end = end, end + 1
            bonsai_node.star_args = self.children[start]

        if self.has_kwargs:
            start = end
            bonsai_node.kw_args = self.children[start]

        return bonsai_node

    def finalize_PyKeyValue(self, bonsai_node):
        bonsai_node.value = self.children[0]
        return bonsai_node

    def finalize_PyModule(self, bonsai_node):
        for child in self.children:
            bonsai_node._add(child)
        return bonsai_node

    def finalize_PyOperator(self, bonsai_node):
        if self.ops:
            ops = zip(self.children, self.ops, self.children[1:])
            return self._expand_compare(bonsai_node.scope, bonsai_node.parent,
                                        ops)

        for child in self.children:
            bonsai_node._add(child)

        return bonsai_node

    def finalize_PyReference(self, bonsai_node):
        if self.children:
            bonsai_node._set_field(self.children[0])

        return bonsai_node