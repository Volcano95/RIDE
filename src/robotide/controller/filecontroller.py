#  Copyright 2008-2009 Nokia Siemens Networks Oyj
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import os

from robot.parsing.tablepopulators import UserKeywordPopulator, TestCasePopulator

from robotide.robotapi import (TestDataDirectory, TestCaseFile, DataRow,
                               is_list_var, is_scalar_var)
from robotide.controller.settingcontroller import (DocumentationController,
        FixtureController, TagsController, TimeoutController,
        TemplateController, ArgumentsController, MetadataController,
        ImportController, ReturnValueController)
from robotide import utils


def DataController(data):
    return TestCaseFileController(data) if isinstance(data, TestCaseFile) \
        else TestDataDirectoryController(data)


class _WithListOperations(object):

    def swap(self, ind1, ind2):
        self._items[ind1], self._items[ind2] = self._items[ind2], self._items[ind1]
        self.mark_dirty()

    def delete(self, index):
        self._items.pop(index)
        self.mark_dirty()

    @property
    def _items(self):
        raise NotImplementedError(self.__class__)

    def mark_dirty(self):
        raise NotImplementedError(self.__class__)


class _DataController(object):

    def __init__(self, data):
        self.data = data
        self.dirty = False
        self.children = self._children(data)

    @property
    def name(self):
        return self.data.name

    @property
    def settings(self):
        return self._settings()

    def _settings(self):
        ss = self.data.setting_table
        return [DocumentationController(self, ss.doc),
                FixtureController(self, ss.suite_setup),
                FixtureController(self, ss.suite_teardown),
                FixtureController(self, ss.test_setup),
                FixtureController(self, ss.test_teardown),
                TagsController(self, ss.force_tags)]

    @property
    def variables(self):
        return VariableTableController(self, self.data.variable_table)

    @property
    def tests(self):
        return TestCaseTableController(self, self.data.testcase_table)

    @property
    def datafile(self):
        return self.data

    @property
    def keywords(self):
        return KeywordTableController(self, self.data.keyword_table)

    @property
    def imports(self):
        return ImportSettingsController(self, self.data.setting_table)

    @property
    def metadata(self):
        return MetadataListController(self, self.data.setting_table)

    def has_been_modified_on_disk(self):
        return False

    def mark_dirty(self):
        self.dirty = True

    def unmark_dirty(self):
        self.dirty = False

    def new_keyword(self, name):
        kw = self.keywords.new(name)
        self.mark_dirty()
        return kw

    def has_format(self):
        return True

    def get_format(self):
        os.path.splitext(self.source)[1].replace('.','')

    def set_format(self, format):
        base = os.path.splitext(self.data.source)[0]
        self.data.source = '%s.%s' % (base, format)

    def validate_keyword_name(self, name):
        return self.keywords.validate_name(name)

    @property
    def source(self):
        return self.data.source

    @property
    def directory(self):
        return self.data.directory


class TestDataDirectoryController(_DataController):

    def _children(self, data):
        return [DataController(child) for child in data.children]

    def has_format(self):
        return self.data.initfile is not None

    def add_suite(self, source):
        if os.path.isdir(source):
            d = TestDataDirectory()
        else:
            d = TestCaseFile()
        d.source = source
        self.data.children.append(d)
        return DataController(d)

    @property
    def source(self):
        return self.data.initfile

    def set_format(self, format):
        self.data.initfile=os.path.join(self.data.source,'__init__.%s' % format)
        self.mark_dirty()


class TestCaseFileController(_DataController):

    def _children(self, data):
        return []

    def _settings(self):
        ss = self.data.setting_table
        return _DataController._settings(self) + \
                [TimeoutController(self, ss.test_timeout),
                 TemplateController(self, ss.test_template)]

    def new_test(self, name):
        return self.tests.new(name)

    def validate_test_name(self, name):
        return self.tests.validate_name(name)


class ResourceFileController(_DataController):

    def _settings(self):
        return [DocumentationController(self, self.data.setting_table.doc)]

    def _children(self, data):
        return []

    def validate_name(self, name):
        for uk in self.data.keyword_table.keywords:
            if uk != name and utils.eq(uk.name, name):
                return 'User keyword with this name already exists.'
        return None


class _TableController(object):
    def __init__(self, parent_controller, table):
        self._parent = parent_controller
        self._table = table

    def mark_dirty(self):
        self._parent.mark_dirty()

    @property
    def dirty(self):
        return self._parent.dirty

    @property
    def datafile(self):
        return self._parent.datafile


class VariableTableController(_TableController, _WithListOperations):

    def __iter__(self):
        return iter(VariableController(v) for v in self._table)

    @property
    def _items(self):
        return self._table.variables

    def add_variable(self, name, value):
        self._table.add(name, value)
        self.mark_dirty()

    def validate_scalar_variable_name(self, name):
        return self._validate_name(_ScalarVarValidator(), name)

    def validate_list_variable_name(self, name):
        return self._validate_name(_ListVarValidator(), name)

    def _validate_name(self, validator, name):
        # TODO: Should communication be changed to use exceptions?
        if not validator(name):
            return '%s variable name must be in format %s{name}' % \
                    (validator.name, validator.prefix)
        if self._name_taken(name):
            return 'Variable with this name already exists.'
        return None

    def _name_taken(self, name):
        return any(utils.eq(name, var.name) for var in self._table)


class _ScalarVarValidator(object):
    __call__ = lambda self, name: is_scalar_var(name)
    name = 'Scalar'
    prefix = '$'

class _ListVarValidator(object):
    __call__ = lambda self, name: is_list_var(name)
    name = 'List'
    prefix = '@'


class VariableController(object):
    def __init__(self, var):
        self._var = var
        self.name = var.name
        self.value= var.value


class _WithItemMovingOperations(object):

    def move_up(self, item):
        items = self._items
        idx = items.index(item)
        if idx  == 0:
            return False
        upper = idx - 1
        items[upper], items[idx] = items[idx], items[upper]
        return True

    def move_down(self, item):
        items = self._items
        idx = items.index(item)
        if idx + 1  == len(items):
            return False
        lower = idx + 1
        items[idx], items[lower] = items[lower], items[idx]
        return True

    @property
    def _items(self):
        raise NotImplementedError(self.__class__)


class TestCaseTableController(_TableController, _WithItemMovingOperations):

    def __iter__(self):
        return iter(TestCaseController(self, t) for t in self._table)

    def __getitem__(self, index):
        return TestCaseController(self, self._table.tests[index])

    def new(self, name):
        tc_controller = TestCaseController(self, self._table.add(name))
        self.mark_dirty()
        return tc_controller

    def validate_name(self, name):
        for t in self._table:
            if t.name == name:
                return 'Test case with this name already exists.'
        return None

    def delete(self, test):
        self._table.tests.remove(test)

    @property
    def _items(self):
        return self._table.tests


class KeywordTableController(_TableController, _WithItemMovingOperations):
    def __iter__(self):
        return iter(UserKeywordController(self, kw) for kw in self._table)

    def __getitem__(self, index):
        return UserKeywordController(self, self._table.keywords[index])

    def new(self, name):
        return UserKeywordController(self, self._table.add(name))

    def validate_name(self, name):
        for kw in self._table:
            if kw.name == name:
                return 'User keyword with this name already exists.'
        return None

    def delete(self, kw):
        self._table.keywords.remove(kw)

    @property
    def _items(self):
        return self._table.keywords


class _WithStepsController(object):
    def __init__(self, parent_controller, data):
        self._parent = parent_controller
        self.data = data
        self._init(data)

    @property
    def name(self):
        return self.data.name

    @property
    def datafile(self):
        return self._parent.datafile

    @property
    def steps(self):
        return self.data.steps

    @property
    def dirty(self):
        return self._parent.dirty

    def mark_dirty(self):
        if self._parent:
            self._parent.mark_dirty()

    def parse_steps_from_rows(self, rows):
        self.data.steps = []
        pop = self._populator(lambda name: self.data)
        for r in rows:
            r = DataRow([''] + r)
            pop.add(r)
        pop.populate()

    def rename(self, new_name):
        self.data.name = new_name
        self.mark_dirty()

    def copy(self, name):
        new = self._parent.new(name)
        for orig, copied in zip(self.settings, new.settings):
            copied.set_value(orig.value)
        new.data.steps = self.data.steps[:]
        return new

    def validate_name(self, name):
        return self._parent.validate_name(name)


class TestCaseController(_WithStepsController):
    _populator = TestCasePopulator

    def _init(self, test):
        self._test = test

    @property
    def settings(self):
        return [DocumentationController(self, self._test.doc),
                FixtureController(self, self._test.setup),
                FixtureController(self, self._test.teardown),
                TagsController(self, self._test.tags),
                TimeoutController(self, self._test.timeout),
                TemplateController(self, self._test.template)]

    def move_up(self):
        return self._parent.move_up(self._test)

    def move_down(self):
        return self._parent.move_down(self._test)

    def delete(self):
        return self._parent.delete(self._test)


class UserKeywordController(_WithStepsController):
    _populator = UserKeywordPopulator

    def _init(self, kw):
        self._kw = kw

    def move_up(self):
        return self._parent.move_up(self._kw)

    def move_down(self):
        return self._parent.move_down(self._kw)

    def delete(self):
        self._parent.delete(self._kw)

    @property
    def settings(self):
        return [DocumentationController(self, self._kw.doc),
                ArgumentsController(self, self._kw.args,),
                TimeoutController(self, self._kw.timeout,),
                # TODO: Wrong class, works right though
                ReturnValueController(self, self._kw.return_,)]


class ImportSettingsController(_TableController, _WithListOperations):

    def __iter__(self):
        return iter(ImportController(imp) for imp in self._items)

    @property
    def _items(self):
        return self._table.imports

    def add_library(self, argstr):
        self._add_import(self._table.add_library, argstr)

    def add_resource(self, name):
        self._add_import(self._table.add_resource, name)

    def add_variables(self, argstr):
        self._add_import(self._table.add_variables, argstr)

    def _add_import(self, adder, argstr):
        adder(*self._split_to_name_and_args(argstr))
        self._parent.mark_dirty()

    def _split_to_name_and_args(self, argstr):
        parts = utils.split_value(argstr)
        return parts[0], parts[1:]


class MetadataListController(_TableController, _WithListOperations):

    def __iter__(self):
        return iter(MetadataController(m) for m in self._items)

    @property
    def _items(self):
        return self._table.metadata

    def add_metadata(self, name, value):
        self._table.add_metadata(name, value)
        self._parent.mark_dirty()


class ControllerTreeWalker(object):

    def __init__(self, function):
        self._function = function

    def iterate(self, controller):
        was_stopped = self._call_function(controller)
        return was_stopped

    def _call_function(self, controller):
        stop = self._function(controller)
        if stop:
            return True
        return self._iterate_children(controller)

    def _iterate_children(self, controller):
        for child in controller.children:
            stop = self._call_function(child)
            if stop:
                return True
        return False
