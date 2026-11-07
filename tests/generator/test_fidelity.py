from sharley.generator.fidelity import path_fidelity
from sharley.schemas import TestCase

ROUTES = ["POST /users/v1/login", "GET /users/v1/{username}", "GET /books/v1", "GET /items/:id", "GET /post/<int:id>/update", "GET /"]


def t(code):
    return TestCase(id="T1", requirement_ids=["R1"], name="n", family="functional", file="tests/a.py", code=code)


def test_real_routes_match_with_params_and_query_strings():
    code = "B+'/users/v1/login'; B+f'/users/v1/{name}'; B+'/books/v1?limit=3'; B+'/items/7'; B+'/post/3/update'"
    f = path_fidelity([t(code)], ROUTES)
    assert f.matched == f.used == 5 and f.score == 1.0 and f.unknown == []


def test_guessed_paths_are_reported():
    f = path_fidelity([t("os.environ.get('LOGIN_PATH', '/login'); B + '/api/me'; B + '/books/v1'")], ROUTES)
    assert f.unknown == ["/api/me", "/login"] and f.matched == 1 and round(f.score, 2) == 0.33


def test_paths_are_deduplicated_and_trailing_slash_tolerated():
    f = path_fidelity([t("'/books/v1/'"), t("'/books/v1'")], ROUTES)
    assert f.used == 1 and f.score == 1.0


def test_no_paths_means_perfect_score_and_prose_is_ignored():
    assert path_fidelity([t("assert True  # see https://x.com/a/b and 5/3")], ROUTES).used == 0
    assert path_fidelity([], ROUTES).score == 1.0


def test_hostile_code_cannot_make_the_regex_blow_up():
    f = path_fidelity([t("'/" + "a" * 50_000 + "'")], ROUTES)
    assert f.used == 1 and f.matched == 0
