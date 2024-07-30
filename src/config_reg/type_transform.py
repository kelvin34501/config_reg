from __future__ import annotations
import sys
import typing


def category_transform(cata):
    if hasattr(cata, "__origin__"):
        return cata.__origin__
    else:
        return cata
