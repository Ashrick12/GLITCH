import unittest

from glitch.analysis.security import SecurityVisitor
from glitch.parsers.docker_parser import DockerParser
from glitch.repr.inter import UnitBlockType
from glitch.tech import Tech


class TestSecurity(unittest.TestCase):
    def __help_test(self, path, n_errors, codes, lines):
        parser = DockerParser()
        inter = parser.parse(path, UnitBlockType.script, False)
        analysis = SecurityVisitor(Tech.docker)
        analysis.config("configs/default.ini")
        errors = list(filter(lambda e: e.code.startswith('sec_'), set(analysis.check(inter))))
        errors = sorted(errors, key=lambda e: (e.path, e.line, e.code))
        self.assertEqual(len(errors), n_errors)
        for i in range(n_errors):
            self.assertEqual(errors[i].code, codes[i])
            self.assertEqual(errors[i].line, lines[i])

    def test_docker_admin(self):
        self.__help_test(
            "tests/security/docker/files/admin.Dockerfile",
            2, ['sec_def_admin', 'sec_def_admin'], [2, 4]
        )

    def test_docker_empty(self):
        self.__help_test(
            "tests/security/docker/files/empty.Dockerfile",
            3, ["sec_empty_pass", "sec_hard_pass", "sec_hard_secr"], [4, 4, 4]
        )
        pass

    def test_docker_full_permission(self):
        self.__help_test(
            "tests/security/docker/files/full_permission.Dockerfile",
            1, ['sec_full_permission_filesystem'], [3]
        )

    def test_docker_hard_secret(self):
        self.__help_test(
            "tests/security/docker/files/hard_secr.Dockerfile",
            2, ["sec_hard_pass", "sec_hard_secr"], [3, 3]
        )

    def test_docker_http(self):
        self.__help_test(
            "tests/security/docker/files/http.Dockerfile",
            1, ["sec_https"], [5]
        )

    def test_docker_int_check(self):
        self.__help_test(
            "tests/security/docker/files/int_check.Dockerfile",
            1, ["sec_no_int_check"], [4]
        )

    def test_docker_inv_bind(self):
        self.__help_test(
            "tests/security/docker/files/inv_bind.Dockerfile",
            1, ["sec_invalid_bind"], [4]
        )

    def test_docker_non_official_image(self):
        self.__help_test(
            "tests/security/docker/files/non_off_image.Dockerfile",
            1, ["sec_non_official_image"], [1]
        )

    def test_docker_obs_command(self):
        self.__help_test(
            "tests/security/docker/files/obs_command.Dockerfile",
            1, ["sec_obsolete_command"], [4]
        )

    def test_docker_susp(self):
        self.__help_test(
            "tests/security/docker/files/susp.Dockerfile",
            1, ["sec_susp_comm"], [3]
        )

    def test_docker_weak_crypt(self):
        self.__help_test(
            "tests/security/docker/files/weak_crypt.Dockerfile",
            1, ["sec_weak_crypt"], [8]
        )
