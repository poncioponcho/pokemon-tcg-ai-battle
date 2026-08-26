"""Standalone entrypoint for the Grim strategic rules pilot."""
from strategic_policy import agent as _policy


def competition_entrypoint(obs):
    return _policy(obs)
