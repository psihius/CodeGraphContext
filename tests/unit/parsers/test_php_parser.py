from pathlib import Path
from unittest.mock import MagicMock

import pytest

from codegraphcontext.tools.languages.php import PhpTreeSitterParser
from codegraphcontext.utils.tree_sitter_manager import get_tree_sitter_manager


@pytest.fixture(scope="module")
def php_parser():
    manager = get_tree_sitter_manager()
    if not manager.is_language_available("php"):
        pytest.skip("PHP tree-sitter grammar is not available in this environment")

    wrapper = MagicMock()
    wrapper.language_name = "php"
    wrapper.language = manager.get_language_safe("php")
    wrapper.parser = manager.create_parser("php")
    return PhpTreeSitterParser(wrapper)


def test_php_variables_capture_all_variable_name_nodes(php_parser, temp_test_dir):
    code = """<?php
class Example
{
    private string $name;

    public function __construct(string $name)
    {
        $local = new Service();
        $copy = $local;
        $this->name = $name;
        echo $copy;
    }
}
"""
    php_file = temp_test_dir / "sample.php"
    php_file.write_text(code)

    result = php_parser.parse(Path(php_file))

    names = [item["name"] for item in result["variables"]]

    assert names.count("$name") == 3
    assert names.count("$local") == 2
    assert names.count("$copy") == 2
    assert names.count("$this") == 1
    assert len(result["variables"]) == 8
