import thesis.parsers.parser as p
import ruamel.yaml as yaml
import os
from thesis.repr.inter import *
from thesis.parsers.ruby_parser import parser_yacc
from pkg_resources import resource_filename
from string import Template
import tempfile
import re

class AnsibleParser(p.Parser):
    def __get_yaml_comments(self, d):
        def extract_from_token(tokenlist):
            res = []
            for token in tokenlist:
                if token is None:
                    continue
                if isinstance(token, list):
                    res += extract_from_token(token)
                else:
                    res.append((token.start_mark.line, token.value))
            return res

        def yaml_comments(d):
            res = []

            if isinstance(d, dict):
                if d.ca.comment is not None:
                    for line, comment in extract_from_token(d.ca.comment):
                        res.append((line, comment))
                for key, val in d.items():
                    for line, comment in yaml_comments(val):
                        res.append((line, comment))
                    if key in d.ca.items:
                        for line, comment in extract_from_token(d.ca.items[key]):
                            res.append((line, comment))
            elif isinstance(d, list):
                if d.ca.comment is not None:
                    for line, comment in extract_from_token(d.ca.comment):
                        res.append((line, comment))
                for idx, item in enumerate(d):
                    for line, comment in yaml_comments(item):
                        res.append((line, comment))
                    if idx in d.ca.items:
                        for line, comment in extract_from_token(d.ca.items[idx]):
                            res.append((line, comment))

            return res

        return list(filter(lambda c: "#" in c[1], \
            [(c[0] + 1, c[1].strip()) for c in yaml_comments(d)]))

    def __parse_tasks(self, module, name, file):
        parsed_file = yaml.YAML().load(file)
        unit_block = UnitBlock(name)

        if (parsed_file == None):
            module.add_block(unit_block)
            return

        for task in parsed_file:
            atomic_unit = AtomicUnit("", "") #FIXME type

            for key, val in task.items():
                # Dependencies
                if key == "include":
                    unit_block.add_dependency(val)
                    break

                if key != "name":
                    if atomic_unit.name == "":
                        atomic_unit.name = key

                    if (isinstance(val, str) or isinstance(val, list)):
                        atomic_unit.add_attribute(Attribute(key, str(val)))
                    else:
                        for atr in val:
                            atomic_unit.add_attribute(Attribute(atr, str(val[atr])))

            # If it was a task without a module we ignore it (e.g. dependency)
            if atomic_unit.name != "":
                unit_block.add_atomic_unit(atomic_unit)

        for comment in self.__get_yaml_comments(parsed_file):
           unit_block.add_comment(Comment(comment[1]))

        module.add_block(unit_block)

    def __parse_vars(self, module, name, file):
        def parse_var(cur_name, map):
            for key, val in map.items():
                if isinstance(val, dict):
                    parse_var(cur_name + key + ".", val)
                else:
                    unit_block.add_variable(Variable(cur_name + key, str(val)))

        parsed_file = yaml.YAML().load(file)
        unit_block = UnitBlock(name)

        if (parsed_file == None):
            module.add_block(unit_block)
            return

        parse_var("", parsed_file)
        module.add_block(unit_block)

    def parse(self, path: str) -> Module:
        def parse_folder(folder, p_function):
            files = [f for f in os.listdir(path + folder) \
                if os.path.isfile(os.path.join(path + folder, f))]
            for file in files:
                with open(path + folder + file) as f:
                    p_function(res, folder + file, f)

        res: Module = Module(os.path.basename(os.path.normpath(path)))
        super().parse_file_structure(res.folder, path)

        parse_folder("/tasks/", self.__parse_tasks)
        parse_folder("/handlers/", self.__parse_tasks)
        parse_folder("/vars/", self.__parse_vars)
        parse_folder("/defaults/", self.__parse_vars)

        return res

class ChefParser(p.Parser):
    def parse(self, path: str) -> Module:
        class Node:
            id: str
            args: list

            def __init__(self, id, args) -> None:
                self.id = id
                self.args = args

            def __repr__(self) -> str:
                return str(self.id)

            def __iter__(self):
                return iter(self.args)

            def __reversed__(self):
                return reversed(self.args)

            @staticmethod
            def check_id(ast, ids):
                return isinstance(ast, Node) and ast.id in ids

            @staticmethod
            def check_node(ast, ids, size):
                return Node.check_id(ast, ids) and len(ast.args) == size

            @staticmethod
            def get_content_bounds(ast, lines):
                def is_bounds(l):
                    return (isinstance(l, list) and len(l) == 2 and isinstance(l[0], int)
                            and isinstance(l[1], int))
                start_line, start_column = float('inf'), float('inf')
                end_line, end_column = 0, 0
                bounded_structures = \
                    ["brace_block", "arg_paren", "string_literal", "string_embexpr", 
                        "aref", "array", "args_add_block"]

                if (isinstance(ast, Node) and len(ast.args) > 0 and is_bounds(ast.args[-1])):
                    start_line, start_column = ast.args[-1][0], ast.args[-1][1]
                    # The second argument counting from the end has the content
                    # of the node (variable name, string...)
                    end_line, end_column = ast.args[-1][0], ast.args[-1][1] + len(ast.args[-2]) - 1

                    # With identifiers we need to consider the : behind them
                    if (Node.check_id(ast, ["@ident"]) 
                    and lines[start_line - 1][start_column - 1] == ":"):
                        start_column -= 1

                elif (isinstance(ast, list) or isinstance(ast, Node)):
                    for arg in ast:
                        bound = Node.get_content_bounds(arg, lines)
                        if bound[0] < start_line:
                            start_line = bound[0]
                        if bound[1] < start_column:
                            start_column = bound[1]
                        if bound[2] > end_line:
                            end_line = bound[2]
                        if bound[3] > end_column:
                            end_column = bound[3]

                    # We have to consider extra characters which correspond
                    # to enclosing characters of these structures
                    if (start_line != float('inf') and Node.check_id(ast, bounded_structures)):
                        r_brackets = ['}', ')', ']', '"', '\'']
                        # Add spaces/brackets in front of last token
                        i = 0
                        for c in lines[end_line - 1][end_column + 1:]:
                            if c.isspace():
                                i += 1
                            elif c in r_brackets:
                                end_column += i + 1
                                break
                            else:
                                break
                        end_column += i

                        l_brackets = ['{', '(', '[', '"', '\'']
                        # Add spaces/brackets behind first token
                        i = 0

                        for c in lines[start_line - 1][:start_column][::-1]:
                            if c.isspace():
                                i += 1
                            elif c in l_brackets:
                                start_column -= i + 1
                                break
                            else:
                                break

                        if (Node.check_id(ast, ['string_embexpr'])):
                            if (lines[start_line - 1][start_column] == "{" and
                                lines[start_line - 1][start_column - 1] == "#"):
                                start_column -= 1

                    # The original AST does not have the start column
                    # of these refs. We need to consider the ::
                    elif Node.check_id(ast, ["top_const_ref"]):
                        start_column -= 2

                return (start_line, start_column, end_line, end_column)

            # FIXME unmatched brackets
            @staticmethod
            def get_content(ast, lines):
                empty_structures = {
                    'string_literal': "''",
                    'hash': "{}",
                    'array': "[]"
                }

                if ((ast.id in empty_structures and len(ast.args) == 0) or
                    (ast.id == 'string_literal' and len(ast.args[0].args) == 0)):
                    return empty_structures[ast.id]

                bounds = Node.get_content_bounds(ast, lines)

                res = ""
                if (bounds[0] == float('inf')):
                    return res

                for l in range(bounds[0] - 1, bounds[2]):
                    if (bounds[0] - 1 == bounds[2] - 1):
                        res += lines[l][bounds[1]:bounds[3] + 1]
                    elif (l == bounds[2] - 1):
                        res += lines[l][:bounds[3] + 1]
                    elif (l == bounds[0] - 1):
                        res += lines[l][bounds[1]:]
                    else:
                        res += lines[l]

                if ((ast.id == "method_add_block") and (ast.args[1].id == "do_block")):
                    res += "end"

                return res.strip()

        class Checker:
            tests_ast_stack: list
            lines: list

            def __init__(self, lines):
                self.tests_ast_stack = []
                self.lines = lines

            def check(self):
                tests, ast = self.pop()
                for test in tests:
                    if test(ast):
                        return True

                return False

            def check_all(self):
                status = True
                while (len(self.tests_ast_stack) != 0 and status):
                    status = self.check()
                return status

            def push(self, tests, ast):
                self.tests_ast_stack.append((tests, ast))

            def pop(self):
                return self.tests_ast_stack.pop()

        class ResourceChecker(Checker):
            atomic_unit: AtomicUnit

            def __init__(self, atomic_unit, lines, ast):
                super().__init__(lines)
                self.push([self.is_block_resource, 
                    self.is_inline_resource], ast)
                self.atomic_unit = atomic_unit

            def is_block_resource(self, ast):
                if (Node.check_node(ast, ["method_add_block"], 2) and 
                    Node.check_node(ast.args[0], ["command"], 2) 
                        and Node.check_node(ast.args[1], ["do_block"], 1)):
                    self.push([self.is_resource_body], ast.args[1])
                    self.push([self.is_resource_def], ast.args[0])
                    return True
                return False

            def is_inline_resource(self, ast):
                if (Node.check_node(ast, ["command"], 2) and 
                    Node.check_id(ast.args[0], ["@ident"]) 
                        and Node.check_node(ast.args[1], ["args_add_block"], 2)):
                    self.push([self.is_resource_body_without_attributes,
                        self.is_inline_resource_name], ast.args[1])
                    self.push([self.is_resource_type], ast.args[0])
                    return True
                return False

            def is_resource_def(self, ast):
                if (Node.check_node(ast.args[0], ["@ident"], 2) 
                  and Node.check_node(ast.args[1], ["args_add_block"], 2)):
                    self.push([self.is_resource_name], ast.args[1])
                    self.push([self.is_resource_type], ast.args[0])
                    return True
                return False

            def is_resource_type(self, ast):
                if (isinstance(ast.args[0], str) and isinstance(ast.args[1], list) \
                    and not ast.args[0] in ["action", "include_recipe", "deprecated_property_alias"]):
                    self.atomic_unit.type = ast.args[0]
                    return True
                return False

            def is_resource_name(self, ast):
                if (isinstance(ast.args[0][0], Node) and ast.args[1] == False):
                    resource_id = ast.args[0][0]
                    self.atomic_unit.name = Node.get_content(resource_id, self.lines)
                    return True
                return False

            def is_inline_resource_name(self, ast):
                if (Node.check_node(ast.args[0][0], ["method_add_block"], 2) 
                    and ast.args[1] == False):
                    resource_id = ast.args[0][0].args[0]
                    self.atomic_unit.name = Node.get_content(resource_id, self.lines)
                    self.push([self.is_attribute], ast.args[0][0].args[1])
                    return True
                return False

            def is_resource_body(self, ast):
                if Node.check_id(ast.args[0], ["bodystmt"]):
                    self.push([self.is_attribute], ast.args[0].args[0])
                    return True
                return False
            
            def is_resource_body_without_attributes(self, ast):
                if (Node.check_id(ast.args[0][0], ["string_literal"]) and ast.args[1] == False):
                    self.atomic_unit.name = Node.get_content(ast.args[0][0], self.lines)
                    return True
                return False

            def is_attribute(self, ast):
                if (Node.check_node(ast, ["method_add_arg"], 2) and Node.check_id(ast.args[0], ["call"])):
                    self.push([self.is_attribute], ast.args[0].args[0])
                elif ((Node.check_id(ast, ["command", "method_add_arg"]) and ast.args[1] != []) or 
                  (Node.check_id(ast, ["method_add_block"]) and 
                  Node.check_id(ast.args[0], ["method_add_arg"]) and 
                  Node.check_id(ast.args[1], ["brace_block"]))):
                    self.atomic_unit.add_attribute(Attribute(
                        Node.get_content(ast.args[0], self.lines), Node.get_content(ast.args[1], self.lines)))
                elif isinstance(ast, Node) or isinstance(ast, list):
                    for arg in reversed(ast):
                        self.push([self.is_attribute], arg)

                return True

        class VariableChecker(Checker):
            variable: Variable

            def __init__(self, lines, ast):
                super().__init__(lines)
                self.variable = Variable("", "")
                self.push([self.is_variable], ast)

            def is_variable(self, ast):
                if Node.check_node(ast, ["assign"], 2):
                    self.variable.name = Node.get_content(ast.args[0], self.lines)
                    self.variable.value = Node.get_content(ast.args[1], self.lines)
                    return True
                return False

        class IncludeChecker(Checker):
            include: str

            def __init__(self, lines, ast):
                super().__init__(lines)
                self.push([self.is_include], ast)

            def is_include(self, ast):
                if (Node.check_node(ast, ["command"], 2) and Node.check_id(ast.args[0], ["@ident"]) 
                  and Node.check_node(ast.args[1], ["args_add_block"], 2)):
                    self.push([self.is_include_name], ast.args[1])
                    self.push([self.is_include_type], ast.args[0])
                    return True
                return False

            def is_include_type(self, ast):
                if (isinstance(ast.args[0], str) and isinstance(ast.args[1], list) 
                  and ast.args[0] == "include_recipe"):
                    return True
                return False

            def is_include_name(self, ast):
                if (Node.check_id(ast.args[0][0], ["string_literal"]) and ast.args[1] == False):
                    self.include = Node.get_content(ast.args[0][0], self.lines)
                    return True
                return False

        def create_ast(l):
            args = []
            for el in l[1:]:
                if isinstance(el, list): 
                    if len(el) > 0 and isinstance(el[0], tuple) and el[0][0] == "id":
                        args.append(create_ast(el))
                    else:
                        arg = []
                        for e in el:
                            if isinstance(e, list) and isinstance(e[0], tuple) and e[0][0] == "id":
                                arg.append(create_ast(e))
                            else:
                                arg.append(e)
                        args.append(arg)
                else:
                    args.append(el)

            return Node(l[0][1], args)

        def transverse_ast(ast, unit_block, lines):
            if (isinstance(ast, list)):
                for arg in ast:
                    if (isinstance(arg, Node) or isinstance(arg, list)):
                        transverse_ast(arg, unit_block, lines)
            else:
                resource_checker = ResourceChecker(AtomicUnit("", ""), lines, ast)
                if (resource_checker.check_all()):
                    unit_block.add_atomic_unit(resource_checker.atomic_unit)
                    return

                variable_checker = VariableChecker(lines, ast)
                if (variable_checker.check_all()):
                    unit_block.add_variable(variable_checker.variable)
                    # variables might have resources associated to it
                    transverse_ast(ast.args[1], unit_block, lines)
                    return

                include_checker = IncludeChecker(lines, ast)
                if (include_checker.check_all()):
                    unit_block.add_dependency(include_checker.include)
                    return

                for arg in ast.args:
                    if (isinstance(arg, Node) or isinstance(arg, list)):
                        transverse_ast(arg, unit_block, lines)

        def parse_file(path, file):
            with open(path + file) as f:
                ripper = resource_filename("thesis.parsers", 'resources/comments.rb.template')
                ripper = open(ripper, "r")
                ripper_script = Template(ripper.read())
                ripper.close()
                ripper_script = ripper_script.substitute({'path': '\"' + path + file + '\"'})

                unit_block: UnitBlock = UnitBlock(file)
                lines = f.readlines()
                
                with tempfile.NamedTemporaryFile(mode="w+") as tmp:
                    tmp.write(ripper_script)
                    tmp.flush()

                    script_ast = os.popen('ruby ' + tmp.name).read()
                    comments, _ = parser_yacc(script_ast)
                    
                    for comment in comments:
                        unit_block.add_comment(Comment(re.sub(r'\\n$', '', comment)))

                script_ast = os.popen('ruby -r ripper -e \'file = \
                    File.open(\"' + path + file + '\")\npp Ripper.sexp(file)\'').read()
                _, program = parser_yacc(script_ast)
                ast = create_ast(program)
                transverse_ast(ast, unit_block, lines)
                res.add_block(unit_block)

        def parse_folder(folder):
            if os.path.exists(path + folder):
                files = [f for f in os.listdir(path + folder) \
                    if os.path.isfile(os.path.join(path + folder, f))]
                for file in files:
                    parse_file(path + folder, file)

        res: Module = Module(os.path.basename(os.path.normpath(path)))
        super().parse_file_structure(res.folder, path)

        parse_folder("/resources/")
        parse_folder("/recipes/")
        parse_folder("/attributes/")

        return res