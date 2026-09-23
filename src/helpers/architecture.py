from typing import TypeVar

from pydantic import BaseModel, ConfigDict

# Reusable generic type variable
T = TypeVar("T")


from typing import Any, get_args


class implements[Proto, Base = object]:
    """
    Generic decorator for statically asserting that a concrete class
    structurally implements a `Protocol`.

    When `Proto` is a `Protocol` class, applying `@implements[Proto]()`
    to a concrete class causes a static type checker such as mypy
    to check that the class structurally satisfies `type[Proto]`,
    in particular `Proto`'s read-only `@property` definitions.

    For a concrete class `C`, this decorator imposes essentially
    the same static compatibility check as:

    ```python
    _check: type[Proto] = C
    ```

    Normal mypy protocol compatibility rules apply, including
    compatibility of member signatures and nested member types.

    At runtime, no conformance check is performed.

    When `Base` and keyword arguments are provided, the concrete
    class is additionally required at runtime to inherit from `Base`
    and to have matching class attributes for those arguments.

    Returns the original class unchanged.

    Note 1: The static type checker neither asserts nor enforces
    that `Proto` is a `Protocol` class; rather, this is mandated
    as a convention in this code base.

    Note 2: Even though not enforced by the static type checker,
    unintended use (i.e., where `Proto` is not a `Protocol` class)
    may tend to fail for other reasons, e.g.:

    - mypy's `[empty-body]` error if `Proto` has properties
    defined with only a signature and `...`);
    - mypy's `[arg-type]` error if `C` does not nominally
    inherit from `Proto`.

    signed off: human (credit to gpt-6-astra-pro for conceiving)
    """

    def __init__(self, **requirements: Any) -> None:
        self.requirements = requirements

    def __call__(self, cls: type[Proto]) -> type[Proto]:
        base: type[Base]  # for static typing
        _, base = get_args(self.__orig_class__)

        if not issubclass(cls, base):
            raise TypeError(
                f"{cls.__qualname__} must inherit from {base.__qualname__}."
            )

        for name, expected in self.requirements.items():
            actual = getattr(cls, name)

            if actual != expected:
                raise TypeError(
                    f"{cls.__qualname__}.{name} must equal "
                    f"{expected!r}; got {actual!r}."
                )

        return cls


class FrozenStrictModel(BaseModel):
    """
    Hardened drop-in replacement for Pydantic `BaseModel`:
    
    - `extra="forbid"` -> reject unknown fields;
    - `frozen=True` -> instances are immutable after creation;
    - `strict=True` -> avoid automatic type coercion.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
    )
