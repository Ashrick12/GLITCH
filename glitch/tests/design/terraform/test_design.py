import unittest

from glitch.analysis.design import DesignVisitor
from glitch.parsers.cmof import TerraformParser
from glitch.tech import Tech

class TestDesign(unittest.TestCase):
    def __help_test(self, path, n_errors, codes, lines):
        parser = TerraformParser()
        inter = parser.parse(path, "script", False)
        analysis = DesignVisitor(Tech.terraform)
        analysis.config("configs/default.ini")
        errors = list(filter(lambda e: e.code.startswith('design_') 
                or e.code.startswith('implementation_'), set(analysis.check(inter))))
        errors = sorted(errors, key=lambda e: (e.path, e.line, e.code))
        self.assertEqual(len(errors), n_errors)
        for i in range(n_errors):
            self.assertEqual(errors[i].code, codes[i])
            self.assertEqual(errors[i].line, lines[i])  
    
    def test_terraform_long_statement(self):
        self.__help_test(
            "tests/design/terraform/files/long_statement.tf",
            1, ["implementation_long_statement"], [6]
        )

    def test_terraform_improper_alignment(self):
        self.__help_test(
            "tests/design/terraform/files/improper_alignment.tf",
            1, 
            [
                "implementation_improper_alignment"
            ], [1]
        )

    def test_terraform_duplicate_block(self):
        self.__help_test(
            "tests/design/terraform/files/duplicate_block.tf",
            2, 
            [
                "design_duplicate_block", 
                "design_duplicate_block", 
            ], [1, 10]
        )

    def test_terraform_avoid_comments(self):
        self.__help_test(
            "tests/design/terraform/files/avoid_comments.tf",
            2, 
            [
                "design_avoid_comments",
                "design_avoid_comments", 
            ], [2, 8]
        )

    def test_terraform_too_many_variables(self):
        self.__help_test(
            "tests/design/terraform/files/too_many_variables.tf",
            1, 
            [
                "implementation_too_many_variables", 
            ], [-1]
        )
