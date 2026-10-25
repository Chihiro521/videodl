import ast

from desktop.build import PublicDefaults


def test_public_build_removes_defaults_without_changing_api_structure():
    original = '''
API_TOKEN = "example-private-service-token"
headers = {"Cookie": "account=example-value", "User-Agent": "Example public user agent"}
def f(url, cookies=None):
    return url, cookies
'''
    transform = PublicDefaults()
    tree = transform.visit(ast.parse(original))
    result = ast.unparse(ast.fix_missing_locations(tree))
    assert "example-private-service-token" not in result
    assert "account=example-value" not in result
    assert "Example public user agent" in result
    assert "def f(url, cookies=None)" in result
    assert len(transform.removed) == 2
