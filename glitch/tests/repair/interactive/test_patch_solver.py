from glitch.repair.interactive.delta_p import *
from glitch.repair.interactive.solver import PatchSolver

statement = PSeq(
    PSeq(
        PSeq(
            PSkip(),
            PLet(
                "state-2",
                PEConst(PStr("present")),
                2,
                PLet(
                    "content-1",
                    PEConst(PStr("<html><body><h1>Hello World</h1></body></html>")),
                    1,
                    PCreate(
                        PEConst(PStr("/var/www/customers/public_html/index.php")),
                        PEVar("content-1"),
                    ),
                )
            ),
        ),
        PLet(
            "mode-3",
            PEConst(PStr("0755")),
            3,
            PChmod(
                PEConst(PStr("/var/www/customers/public_html/index.php")),
                PEVar("mode-3"),
            ),
        ),
    ),
    PLet(
        "owner-4",
        PEConst(PStr("web_admin")),
        4,
        PChown(
            PEConst(PStr("/var/www/customers/public_html/index.php")),
            PEVar("owner-4"),
        ),
    ),
)
    

def test_patch_solver_mode():
    filesystem = FileSystemState()
    filesystem.state["/var/www/customers/public_html/index.php"] = File(
        mode="0777",
        owner="web_admin",
        content="<html><body><h1>Hello World</h1></body></html>",
    )

    solver = PatchSolver(statement, filesystem)
    model = solver.solve()
    assert model is not None
    assert model[solver.sum_var] == 3
    assert model[solver.unchanged[1]] == 1
    assert model[solver.unchanged[2]] == 1
    assert model[solver.unchanged[3]] == 0
    assert model[solver.unchanged[4]] == 1
    assert model[solver.vars["content-1"]] == "<html><body><h1>Hello World</h1></body></html>"
    assert model[solver.vars["mode-3"]] == "0777"
    assert model[solver.vars["owner-4"]] == "web_admin"


def test_patch_solver_delete_file():    
    filesystem = FileSystemState()
    filesystem.state["/var/www/customers/public_html/index.php"] = Nil()

    # TODO: For this to work I need to change the way ensures are handled
    # The author of the paper uses the construct If to do this
    # I have to decide if I want to do that or not
    # I think it is possible to do it in a simpler way, similar
    # to the other cases

    solver = PatchSolver(statement, filesystem)
    model = solver.solve()
    assert model is not None