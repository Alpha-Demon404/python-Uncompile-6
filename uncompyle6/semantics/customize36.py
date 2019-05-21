#  Copyright (c) 2019 by Rocky Bernstein
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""Isolate Python 3.6 version-specific semantic actions here.
"""

from spark_parser.ast import GenericASTTraversalPruningException
from uncompyle6.scanners.tok import Token
from uncompyle6.semantics.helper import (
    flatten_list, escape_string, strip_quotes
    )
from uncompyle6.semantics.consts import (
    INDENT_PER_LEVEL, PRECEDENCE, TABLE_DIRECT, TABLE_R)

def escape_format(s):
    return s.replace('\r', '\\r').\
        replace('\n', '\\n').\
        replace("'''", '"""')

#######################
# Python 3.6+ Changes #
#######################

def customize_for_version36(self, version):
    PRECEDENCE['call_kw']     = 0
    PRECEDENCE['call_kw36']   = 1
    PRECEDENCE['call_ex']     = 1
    PRECEDENCE['call_ex_kw']  = 1
    PRECEDENCE['call_ex_kw2'] = 1
    PRECEDENCE['call_ex_kw3'] = 1
    PRECEDENCE['call_ex_kw4'] = 1
    PRECEDENCE['unmap_dict']  = 0
    PRECEDENCE['formatted_value1'] = 100

    TABLE_DIRECT.update({
        'tryfinally36':     ( '%|try:\n%+%c%-%|finally:\n%+%c%-\n\n',
                              (1, 'returns'), 3 ),
        'func_args36':      ( "%c(**", 0),
        'try_except36':     ( '%|try:\n%+%c%-%c\n\n', 1, -2 ),
        'except_return':    ( '%|except:\n%+%c%-', 3 ),
        'unpack_list':      ( '*%c', (0, 'list') ),
        'tryfinally_return_stmt':
              ( '%|try:\n%+%c%-%|finally:\n%+%|return%-\n\n', 1 ),

        'async_for_stmt36':  (
            '%|async for %c in %c:\n%+%c%-%-\n\n',
            (9, 'store'), (1, 'expr'), (18, 'for_block') ),

        'call_ex' : (
            '%c(%p)',
            (0, 'expr'), (1, 100)),

    })

    TABLE_R.update({
        'CALL_FUNCTION_EX': ('%c(*%P)', 0, (1, 2, ', ', 100)),
        # Not quite right
        'CALL_FUNCTION_EX_KW': ('%c(**%C)', 0, (2, 3, ',')),
        })

    def build_unpack_tuple_with_call(node):
        n = node[0]
        if n == 'expr':
            n = n[0]
        if n == 'tuple':
            self.call36_tuple(n)
            first = 1
            sep = ', *'
        elif n == 'LOAD_CONST':
            value = self.format_pos_args(n)
            self.f.write(value)
            first = 1
            sep = ', *'
        else:
            first = 0
            sep = '*'

        buwc = node[-1]
        assert buwc.kind.startswith('BUILD_TUPLE_UNPACK_WITH_CALL')
        for n in node[first:-1]:
            self.f.write(sep)
            self.preorder(n)
            sep = ', *'
            pass
        self.prune()
        return
    self.n_build_tuple_unpack_with_call = build_unpack_tuple_with_call

    def build_unpack_map_with_call(node):
        n = node[0]
        if n == 'expr':
            n = n[0]
        if n == 'dict':
            self.call36_dict(n)
            first = 1
            sep = ', **'
        else:
            first = 0
            sep = '**'
        for n in node[first:-1]:
            self.f.write(sep)
            self.preorder(n)
            sep = ', **'
            pass
        self.prune()
        return
    self.n_build_map_unpack_with_call = build_unpack_map_with_call

    def call_ex_kw(node):
        """Handle CALL_FUNCTION_EX 1 (have KW) but with
        BUILD_MAP_UNPACK_WITH_CALL"""

        expr = node[1]
        assert expr == 'expr'

        value = self.format_pos_args(expr)
        if value == '':
            fmt = "%c(%p)"
        else:
            fmt = "%%c(%s, %%p)" % value

        self.template_engine(
            (fmt,
            (0, 'expr'), (2, 'build_map_unpack_with_call', 100)), node)

        self.prune()
    self.n_call_ex_kw = call_ex_kw

    def call_ex_kw2(node):
        """Handle CALL_FUNCTION_EX 2  (have KW) but with
        BUILD_{MAP,TUPLE}_UNPACK_WITH_CALL"""

        assert node[1] == 'build_tuple_unpack_with_call'
        value = self.format_pos_args(node[1])
        if value == '':
            fmt = "%c(%p)"
        else:
            fmt = "%%c(%s, %%p)" % value

        self.template_engine(
            (fmt,
            (0, 'expr'), (2, 'build_map_unpack_with_call', 100)), node)

        self.prune()
    self.n_call_ex_kw2 = call_ex_kw2

    def call_ex_kw3(node):
        """Handle CALL_FUNCTION_EX 1 (have KW) but without
        BUILD_MAP_UNPACK_WITH_CALL"""
        self.preorder(node[0])
        self.write('(')

        value = self.format_pos_args(node[1][0])
        if value == '':
            pass
        else:
            self.write(value)
            self.write(', ')

        self.write('*')
        self.preorder(node[1][1])
        self.write(', ')

        kwargs = node[2]
        if kwargs == 'expr':
            kwargs = kwargs[0]
        if kwargs == 'dict':
            self.call36_dict(kwargs)
        else:
            self.write('**')
            self.preorder(kwargs)
        self.write(')')
        self.prune()
    self.n_call_ex_kw3 = call_ex_kw3

    def call_ex_kw4(node):
        """Handle CALL_FUNCTION_EX {1 or 2} but without
        BUILD_{MAP,TUPLE}_UNPACK_WITH_CALL"""
        self.preorder(node[0])
        self.write('(')
        args = node[1][0]
        if args == 'tuple':
            if self.call36_tuple(args) > 0:
                self.write(', ')
                pass
            pass
        else:
            self.write('*')
            self.preorder(args)
            self.write(', ')
            pass

        kwargs = node[2]
        if kwargs == 'expr':
            kwargs = kwargs[0]
        call_function_ex = node[-1]
        assert (call_function_ex == 'CALL_FUNCTION_EX_KW'
                or (self.version >= 3.6 and call_function_ex == 'CALL_FUNCTION_EX'))
        # FIXME: decide if the below test be on kwargs == 'dict'
        if (call_function_ex.attr & 1 and
            (not isinstance(kwargs, Token) and kwargs != 'attribute')
            and not kwargs[0].kind.startswith('kvlist')):
            self.call36_dict(kwargs)
        else:
            self.write('**')
            self.preorder(kwargs)
        self.write(')')
        self.prune()
    self.n_call_ex_kw4 = call_ex_kw4

    def format_pos_args(node):
        """
        Positional args should format to:
        (*(2, ), ...) -> (2, ...)
        We remove starting and trailing parenthesis and ', ' if
        tuple has only one element.
        """
        value = self.traverse(node, indent='')
        if value.startswith('('):
            assert value.endswith(')')
            value = value[1:-1].rstrip(" ") # Remove starting '(' and trailing ')' and additional spaces
            if value == '':
                pass # args is empty
            else:
                if value.endswith(','): # if args has only one item
                    value = value[:-1]
        return value
    self.format_pos_args = format_pos_args

    def call36_tuple(node):
        """
        A tuple used in a call, these are like normal tuples but they
        don't have the enclosing parenthesis.
        """
        assert node == 'tuple'
        # Note: don't iterate over last element which is a
        # BUILD_TUPLE...
        flat_elems = flatten_list(node[:-1])

        self.indent_more(INDENT_PER_LEVEL)
        sep = ''

        for elem in flat_elems:
            if elem in ('ROT_THREE', 'EXTENDED_ARG'):
                continue
            assert elem == 'expr'
            line_number = self.line_number
            value = self.traverse(elem)
            if line_number != self.line_number:
                sep += '\n' + self.indent + INDENT_PER_LEVEL[:-1]
            self.write(sep, value)
            sep = ', '

        self.indent_less(INDENT_PER_LEVEL)
        return len(flat_elems)
    self.call36_tuple = call36_tuple

    def call36_dict(node):
        """
        A dict used in a call_ex_kw2, which are a dictionary items expressed
        in a call. This should format to:
             a=1, b=2
        In other words, no braces, no quotes around keys and ":" becomes
        "=".

        We will source-code use line breaks to guide us when to break.
        """
        p = self.prec
        self.prec = 100

        self.indent_more(INDENT_PER_LEVEL)
        sep = INDENT_PER_LEVEL[:-1]
        line_number = self.line_number

        if  node[0].kind.startswith('kvlist'):
            # Python 3.5+ style key/value list in dict
            kv_node = node[0]
            l = list(kv_node)
            i = 0

            length = len(l)
            # FIXME: Parser-speed improved grammars will have BUILD_MAP
            # at the end. So in the future when everything is
            # complete, we can do an "assert" instead of "if".
            if kv_node[-1].kind.startswith("BUILD_MAP"):
                length -= 1

            # Respect line breaks from source
            while i < length:
                self.write(sep)
                name = self.traverse(l[i], indent='')
                # Strip off beginning and trailing quotes in name
                name = name[1:-1]
                if i > 0:
                    line_number = self.indent_if_source_nl(line_number,
                                                           self.indent + INDENT_PER_LEVEL[:-1])
                line_number = self.line_number
                self.write(name, '=')
                value = self.traverse(l[i+1], indent=self.indent+(len(name)+2)*' ')
                self.write(value)
                sep = ", "
                if line_number != self.line_number:
                    sep += "\n" + self.indent + INDENT_PER_LEVEL[:-1]
                    line_number = self.line_number
                i += 2
                pass
        elif node[-1].kind.startswith('BUILD_CONST_KEY_MAP'):
            keys_node = node[-2]
            keys = keys_node.attr
            # from trepan.api import debug; debug()
            assert keys_node == 'LOAD_CONST' and isinstance(keys, tuple)
            for i in range(node[-1].attr):
                self.write(sep)
                self.write(keys[i], '=')
                value = self.traverse(node[i], indent='')
                self.write(value)
                sep = ", "
                if line_number != self.line_number:
                    sep += "\n" + self.indent + INDENT_PER_LEVEL[:-1]
                    line_number = self.line_number
                    pass
                pass
        else:
            self.write("**")
            try:
                self.default(node)
            except GenericASTTraversalPruningException:
                pass

        self.prec = p
        self.indent_less(INDENT_PER_LEVEL)
        return
    self.call36_dict = call36_dict

    def n_call_kw36(node):
        self.template_engine(("%p(", (0, 100)), node)
        keys = node[-2].attr
        num_kwargs = len(keys)
        num_posargs = len(node) - (num_kwargs + 2)
        n = len(node)
        assert n >= len(keys)+1, \
          'not enough parameters keyword-tuple values'
        sep = ''

        line_number = self.line_number
        for i in range(1, num_posargs):
            self.write(sep)
            self.preorder(node[i])
            if line_number != self.line_number:
                sep = ",\n" + self.indent + "  "
            else:
                sep = ", "
            line_number = self.line_number

        i = num_posargs
        j = 0
        # FIXME: adjust output for line breaks?
        while i < n-2:
            self.write(sep)
            self.write(keys[j] + '=')
            self.preorder(node[i])
            if line_number != self.line_number:
                sep = ",\n" + self.indent + "  "
            else:
                sep = ", "
            i += 1
            j += 1
        self.write(')')
        self.prune()
        return
    self.n_call_kw36 = n_call_kw36


    FSTRING_CONVERSION_MAP = {1: '!s', 2: '!r', 3: '!a', 'X':':X'}

    def n_except_suite_finalize(node):
        if node[1] == 'returns' and self.hide_internal:
            # Process node[1] only.
            # The code after "returns", e.g. node[3], is dead code.
            # Adding it is wrong as it dedents and another
            # exception handler "except_stmt" afterwards.
            # Note it is also possible that the grammar is wrong here.
            # and this should not be "except_stmt".
            self.indent_more()
            self.preorder(node[1])
            self.indent_less()
        else:
            self.default(node)
        self.prune()
    self.n_except_suite_finalize = n_except_suite_finalize

    def n_formatted_value(node):
        if node[0] == 'LOAD_CONST':
            value = node[0].attr
            if isinstance(value, tuple):
                self.write(node[0].attr)
            else:
                self.write(escape_string(node[0].attr))
            self.prune()
        else:
            self.default(node)
    self.n_formatted_value = n_formatted_value

    def n_formatted_value_attr(node):
        f_conversion(node)
        fmt_node = node.data[3]
        if fmt_node == 'expr' and fmt_node[0] == 'LOAD_CONST':
            node.string = escape_format(fmt_node[0].attr)
        else:
            node.string = fmt_node
        self.default(node)
    self.n_formatted_value_attr = n_formatted_value_attr

    def f_conversion(node):
        fmt_node = node.data[1]
        if fmt_node == 'expr' and fmt_node[0] == 'LOAD_CONST':
            data = fmt_node[0].attr
        else:
            data = fmt_node.attr
        node.conversion = FSTRING_CONVERSION_MAP.get(data, '')
        return node.conversion

    def n_formatted_value1(node):
        expr = node[0]
        assert expr == 'expr'
        value = self.traverse(expr, indent='')
        conversion = f_conversion(node)
        f_str = "f%s" % escape_string("{%s%s}" % (value, conversion))
        self.write(f_str)
        self.prune()

    self.n_formatted_value1 = n_formatted_value1

    def n_formatted_value2(node):
        p = self.prec
        self.prec = 100

        expr = node[0]
        assert expr == 'expr'
        value = self.traverse(expr, indent='')
        format_value_attr = node[-1]
        assert format_value_attr == 'FORMAT_VALUE_ATTR'
        attr = format_value_attr.attr
        if attr == 4:
            assert node[1] == 'expr'
            fmt = strip_quotes(self.traverse(node[1], indent=''))
            conversion = ":%s" % fmt
        else:
            conversion = FSTRING_CONVERSION_MAP.get(attr, '')

        f_str = "f%s" % escape_string("{%s%s}" % (value, conversion))
        self.write(f_str)

        self.prec = p
        self.prune()
    self.n_formatted_value2 = n_formatted_value2

    def n_joined_str(node):
        p = self.prec
        self.prec = 100

        result = ''
        for expr in node[:-1]:
            assert expr == 'expr'
            value = self.traverse(expr, indent='')
            if expr[0].kind.startswith('formatted_value'):
                # remove leading 'f'
                assert value.startswith('f')
                value = value[1:]
                pass
            else:
                # {{ and }} in Python source-code format strings mean
                # { and } respectively. But only when *not* part of a
                # formatted value. However in the LOAD_CONST
                # bytecode, the escaping of the braces has been
                # removed. So we need to put back the braces escaping in
                # reconstructing the source.
                assert expr[0] == 'LOAD_CONST'
                value = value.replace("{", "{{").replace("}", "}}")

            # Remove leading quotes
            result += strip_quotes(value)
            pass
        self.write('f%s' % escape_string(result))

        self.prec = p
        self.prune()
    self.n_joined_str = n_joined_str


    # def kwargs_only_36(node):
    #     keys = node[-1].attr
    #     num_kwargs = len(keys)
    #     values = node[:num_kwargs]
    #     for i, (key, value) in enumerate(zip(keys, values)):
    #         self.write(key + '=')
    #         self.preorder(value)
    #         if i < num_kwargs:
    #             self.write(',')
    #     self.prune()
    #     return
    # self.n_kwargs_only_36 = kwargs_only_36

    def starred(node):
        l = len(node)
        assert l > 0
        pos_args = node[0]
        if pos_args == 'expr':
            pos_args = pos_args[0]
        if pos_args == 'tuple':
            build_tuple = pos_args[0]
            if build_tuple.kind.startswith('BUILD_TUPLE'):
                tuple_len = 0
            else:
                tuple_len = len(node) - 1
            star_start = 1
            template = '%C', (0, -1, ', ')
            self.template_engine(template, pos_args)
            if tuple_len == 0:
                self.write("*()")
                # That's it
                self.prune()
            self.write(', ')
        else:
            star_start = 0
        if l > 1:
            template = ( '*%C', (star_start, -1, ', *') )
        else:
            template = ( '*%c', (star_start, 'expr') )

        self.template_engine(template, node)
        self.prune()

    self.n_starred = starred

    def return_closure(node):
        # Nothing should be output here
        self.prune()
        return
    self.n_return_closure = return_closure