"""Shared pytest fixtures and helpers, all driving the real shengji engine."""

import pytest

from shengji import Game, GamePhase


@pytest.fixture
def fresh_state():
    """A freshly reset game (DEALING phase) and its Game instance."""
    game = Game(num_players=6)
    state = game.reset(dealer_id=0)
    return game, state


def advance_to_phase(game, state, target: GamePhase, max_steps: int = 3000):
    """Drive the game by always taking legal_actions[0] until `target` is reached.

    Returns the state at the moment it first enters `target`. Raises if the game
    finishes or stalls without reaching it.
    """
    steps = 0
    while state.phase != target:
        if state.phase == GamePhase.SCORING:
            raise AssertionError(f"Reached SCORING before {target.name}")
        if not state.legal_actions:
            raise AssertionError(f"No legal actions in {state.phase.name}")
        state, _ = game.step(state, state.legal_actions[0])
        steps += 1
        if steps > max_steps:
            raise AssertionError(f"Did not reach {target.name} within {max_steps} steps")
    return state
