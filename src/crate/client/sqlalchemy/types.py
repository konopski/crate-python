# -*- coding: utf-8; -*-
#
# Licensed to CRATE Technology GmbH ("Crate") under one or more contributor
# license agreements.  See the NOTICE file distributed with this work for
# additional information regarding copyright ownership.  Crate licenses
# this file to you under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.  You may
# obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  See the
# License for the specific language governing permissions and limitations
# under the License.
#
# However, if you have executed another commercial license agreement
# with Crate these terms will supersede the license and you may use the
# software solely pursuant to the terms of the relevant commercial agreement.

import sqlalchemy.types as sqltypes
from sqlalchemy.sql import operators
from sqlalchemy.ext.mutable import Mutable


class MutableList(Mutable, list):
    @classmethod
    def coerce(cls, key, value):
        """ Convert plain list to MutableList """
        if not isinstance(value, MutableList):
            if isinstance(value, list):
                return MutableList(value)
            else:
                return MutableList([value])
        else:
            return value

    def __init__(self, initval=None):
        list.__init__(self, initval or [])

    def __setitem__(self, key, value):
        list.__setitem__(self, key, value)
        self.changed()

    def append(self, item):
        list.append(self, item)
        self.changed()

    def insert(self, idx, item):
        list.insert(self, idx, item)
        self.changed()

    def __setslice__(self, i, j, other):
        list.__setslice__(self, i, j, other)
        self.changed()

    def extend(self, iterable):
        list.extend(self, iterable)
        self.changed()

    def pop(self, index=-1):
        list.pop(self, index)
        self.changed()

    def remove(self, item):
        list.remove(self, item)
        self.changed()


class MutableDict(Mutable, dict):

    @classmethod
    def coerce(cls, key, value):
        "Convert plain dictionaries to MutableDict."

        if not isinstance(value, MutableDict):
            if isinstance(value, dict):
                return MutableDict(value)

            # this call will raise ValueError
            return Mutable.coerce(key, value)
        else:
            return value

    def __init__(self, initval=None):
        initval = initval or {}
        self._changed_keys = set()
        self._deleted_keys = set()
        dict.__init__(self, initval)

    def __setitem__(self, key, value):
        dict.__setitem__(self, key, value)
        self._deleted_keys.discard(key)
        self._changed_keys.add(key)
        self.changed()

    def __delitem__(self, key):
        dict.__delitem__(self, key)
        self._deleted_keys.add(key)
        self.changed()


class _Craty(sqltypes.UserDefinedType):

    class Comparator(sqltypes.TypeEngine.Comparator):

        def __getitem__(self, key):
            return self._binary_operate(self.expr, operators.getitem, key)

    type = MutableDict
    comparator_factory = Comparator


Object = Craty = MutableDict.as_mutable(_Craty)


class _ObjectArray(sqltypes.UserDefinedType):

    class Comparator(sqltypes.TypeEngine.Comparator):
        def __getitem__(self, key):
            return self._binary_operate(self.expr, operators.getitem, key)

    type = MutableList
    comparator_factory = Comparator


ObjectArray = MutableList.as_mutable(_ObjectArray)
