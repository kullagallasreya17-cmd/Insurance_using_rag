import importlib.util


def test_langchain_google_genai_is_installed():
    assert importlib.util.find_spec("langchain_google_genai") is not None
