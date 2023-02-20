import ast
import os.path
from dataclasses import dataclass, field

import bashlex
from dockerfile_parse import DockerfileParser

import glitch.parsers.parser as p
from glitch.repr.inter import Module, Project, UnitBlockType, UnitBlock, Variable, AtomicUnit, Comment, Attribute


@dataclass
class DFPStructure:
    content: str
    endline: int
    instruction: str
    startline: int
    value: str


class DockerParser(p.Parser):
    __FILE_EXTENSIONS = ["iso", "tar", "tar.gz", "tar.bzip2", "zip",
                         "rar", "gzip", "gzip2", "deb", "rpm", "sh", "run", "bin"]

    def parse_file(self, path: str, type: UnitBlockType) -> UnitBlock:
        with open(path) as f:
            dfp = DockerfileParser()
            dfp.content = f.read()
            structure = [DFPStructure(**s) for s in dfp.structure]

            stage_indexes = [i for i, e in enumerate(structure) if e.instruction == 'FROM']
            if len(stage_indexes) > 1:
                main_block = UnitBlock("", type)
                stages = self.__get_stages(stage_indexes, structure)
                for name, s in stages.items():
                    main_block.add_unit_block(self.__parse_stage(name, path, UnitBlockType.block, s))
            else:
                self.__add_user_tag(structure)
                main_block = self.__parse_stage(dfp.baseimage, path, type, structure)
            main_block.path = path
            return main_block

    def parse_folder(self, path: str) -> Project:
        project = Project(os.path.basename(os.path.normpath(path)))
        blocks, modules = self._parse_folder(path)
        project.blocks = blocks
        project.modules = modules

        return project

    def parse_module(self, path: str) -> Module:
        module = Module(os.path.basename(os.path.normpath(path)), path)
        blocks, modules = self._parse_folder(path)
        module.blocks = blocks
        module.modules = modules
        return module

    def _parse_folder(self, path: str) -> tuple[list[UnitBlock], list[Module]]:
        files = [os.path.join(path, f) for f in os.listdir(path)]
        dockerfiles = [f for f in files if os.path.isfile(f) and "Dockerfile" in os.path.basename(f)]
        modules = [f for f in files if os.path.isdir(f) and DockerParser._contains_dockerfiles(f)]

        blocks = [self.parse_file(f, UnitBlockType.script) for f in dockerfiles]
        modules = [self.parse_module(f) for f in modules]
        return blocks, modules

    @staticmethod
    def _contains_dockerfiles(path: str) -> bool:
        if not os.path.exists(path):
            return False
        if not os.path.isdir(path):
            return "Dockerfile" in os.path.basename(path)
        for f in os.listdir(path):
            contains_dockerfiles = DockerParser._contains_dockerfiles(os.path.join(path, f))
            if contains_dockerfiles:
                return True
        return False

    @staticmethod
    def __parse_stage(name: str, path: str, unit_type: UnitBlockType, structure: list[DFPStructure]) -> UnitBlock:
        u = UnitBlock(name, unit_type)
        u.path = path
        for s in structure:
            DockerParser.__parse_instruction(s, u)

        DockerParser.__merge_download_commands(u)
        return u

    @staticmethod
    def __parse_instruction(element: DFPStructure, unit_block: UnitBlock):
        instruction = element.instruction
        if instruction in ['ENV', 'USER', 'ARG', 'LABEL']:
            unit_block.add_variable(DockerParser.__create_variable_block(element))
        elif instruction == 'FROM':
            au = AtomicUnit(element.value.split(" ")[0], "image")
            au.line = element.startline + 1
            unit_block.add_atomic_unit(au)
        elif instruction == 'COMMENT':
            c = Comment(element.value)
            c.line = element.startline + 1
            unit_block.add_comment(c)
        elif instruction in ['RUN', 'CMD', 'ENTRYPOINT']:
            c_parser = CommandParser(element.value)
            aus = c_parser.parse_command()
            for au in aus:
                au.line = element.startline
            unit_block.atomic_units += aus
        elif instruction == 'ONBUILD':
            dfp = DockerfileParser()
            dfp.content = element.value
            element = DFPStructure(**dfp.structure[0])
            DockerParser.__parse_instruction(element, unit_block)
        elif instruction == 'COPY':
            au = AtomicUnit("", "copy")
            src, dest = [v for v in element.value.split(" ") if not v.startswith("--")]
            au.add_attribute(Attribute('src', src, False))
            au.add_attribute(Attribute('dest', dest, False))
            unit_block.add_atomic_unit(au)
        elif instruction in ['ADD', 'VOLUME', 'WORKDIR']:
            pass
        elif instruction in ['STOPSIGNAL', 'HEALTHCHECK', 'SHELL']:
            pass
        elif instruction == 'EXPOSE':
            pass

    @staticmethod
    def __get_stages(stage_indexes: list[int], structure: list[DFPStructure]) -> dict[str, list[DFPStructure]]:
        stages = {}
        for i, stage_i in enumerate(stage_indexes):
            stage_image = structure[stage_i].value.split(" ")[0]
            stage_start = stage_i if i != 0 else 0
            stage_end = len(structure) if i == len(stage_indexes) - 1 else stage_indexes[i + 1]
            stages[stage_image] = DockerParser.__get_stage_structure(structure, stage_start, stage_end)
        return stages

    @staticmethod
    def __get_stage_structure(structure: list[DFPStructure], stage_start: int, stage_end: int):
        sub_structure = structure[stage_start:stage_end].copy()
        DockerParser.__add_user_tag(sub_structure)
        return sub_structure

    @staticmethod
    def __create_variable_block(element: DFPStructure) -> Variable:
        v: Variable
        if element.instruction == 'USER':
            v = Variable("user", element.value, False)
        elif element.instruction == 'ARG':
            value = element.value.split(",")
            arg = value[0]
            default = value[1] if len(value) == 2 else None
            v = Variable(arg, default if default else "ARG", True)
        elif element.instruction == 'ENV':  # ENV Missing support for multiple values
            split_char = "=" if "=" in element.value else " "
            assert len(element.value.split(split_char)) == 2
            env, value = element.value.split(split_char)
            v = Variable(env, value, "$" in value)
        else:  # LABEL
            label, value = element.value.split("=")
            v = Variable(label, value, False)

        v.line = element.startline + 1
        return v

    @staticmethod
    def __has_user_tag(structure: list[DFPStructure]) -> bool:
        return bool(s for s in structure if s.instruction == "USER")

    @staticmethod
    def __add_user_tag(structure: list[DFPStructure]):
        if len([s for s in structure if s.instruction == "USER"]) > 0:
            return

        index, line = -1, -1
        for i, s in enumerate(structure):
            if s.instruction == 'FROM':
                index = i
                line = s.startline
                break
        structure.insert(index + 1, DFPStructure("USER root", line, "USER", line, "root"))

    @staticmethod
    def __merge_download_commands(unit_block: UnitBlock):
        download_units = [a for a in unit_block.atomic_units if DockerParser.__is_download(a)]
        for d in download_units:
            file = DockerParser.__get_atomic_file_name(d)
            d.add_attribute(Attribute("url", d.name, False))
            d.name = ""
            f_manipulations = [au for au in unit_block.atomic_units if DockerParser.__get_atomic_file_name(au) == file]

            for au in f_manipulations:
                if au.type in ["gpg", "checksum", "md5sum"]:
                    d.add_attribute(Attribute(au.type, "true", False))
                    unit_block.atomic_units.remove(au)

    @staticmethod
    def __is_download(a: AtomicUnit) -> bool:
        # TODO: Improve download verification
        return a.type in ["wget"]

    @staticmethod
    def __get_atomic_file_name(a: AtomicUnit):
        file_name = a.name.split("/")[-1]
        if file_name.split(".")[-1] not in DockerParser.__FILE_EXTENSIONS:
            return None
        return file_name


@dataclass
class ShellCommand:
    sudo: bool
    command: str
    args: list[str]
    options: dict[str, str | bool | int | float] = field(default_factory=dict)
    main_arg: str | None = None

    def to_atomic_unit(self) -> AtomicUnit:
        au = AtomicUnit(self.main_arg, self.command)
        if self.sudo:
            au.add_attribute(Attribute("sudo", "True", False))
        for key, value in self.options.items():
            has_variable = "$" in value if type(value) is str else False
            au.add_attribute(Attribute(key, value, has_variable))
        return au


class CommandParser:
    def __init__(self, command: str):
        if command.startswith("["):
            c_list = ast.literal_eval(command)
            command = " ".join(c_list)
        self.command = command

    def parse_command(self) -> list[AtomicUnit]:
        commands = self.__get_sub_commands()
        aus = []
        for c in commands:
            try:
                aus.append(self.__parse_single_command(c))
            except IndexError:
                pass
        return aus

    @staticmethod
    def __parse_single_command(command: list[str]) -> AtomicUnit:
        sudo = command[0] == "sudo"
        name_index = 0 if not sudo else 1
        command_type = command[name_index]
        c = ShellCommand(sudo=sudo, command=command_type, args=command[name_index + 1:])
        CommandParser.__parse_shell_command(c)
        return c.to_atomic_unit()

    @staticmethod
    def __parse_shell_command(command: ShellCommand):
        if command.command == "chmod":
            command.main_arg = command.args[-1]
            command.options["mode"] = command.args[0]
        else:
            CommandParser.__parse_general_command(command)

    @staticmethod
    def __parse_general_command(command: ShellCommand):
        args = command.args.copy()
        main_arg_index = -1 if not args[-1].startswith("-") else 0
        main_arg = args[main_arg_index]
        del args[main_arg_index]
        command.main_arg = main_arg

        for i, o in enumerate(args):
            if not o.startswith("-"):
                continue

            o = o.lstrip("-")
            if "=" in o:
                option = o.split("=")
                command.options[option[0]] = option[1]
                continue

            if len(args) == i + 1 or args[i + 1].startswith("-"):
                command.options[o] = True
            else:
                command.options[o] = args[i + 1]

    def __get_sub_commands(self) -> list[list[str]]:
        commands = []
        tmp = []
        for part in bashlex.split(self.command):
            if part in ['&&', '&', '|']:
                commands.append(tmp)
                tmp = []
                continue
            tmp.append(part)
        commands.append(tmp)
        return commands
