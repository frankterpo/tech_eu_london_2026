import pytest
from click.exceptions import Exit

from agent.commands.loop import run_loop


def test_loop_rejects_invalid_iterations():
    with pytest.raises(Exit):
        run_loop("Create invoice", iters=0)

    with pytest.raises(Exit):
        run_loop("Create invoice", iters=11)
