"""
Based on the Acme architecture description language
as conceptualized in the 1997 paper:
<https://dl.acm.org/doi/abs/10.5555/782010.782017>

signed off: human
"""

from typing import Protocol, final


class EntityProtocol(Protocol):
    """
    An Acme entity protocol.

    In this Python realization,
    this may have nested classes
    referencing each other,
    which must use fully qualified
    names, which works for static
    annotation checking downstream,
    for example:

    ```python
    from typing import Protocol

    # Structural static check like `_: type[P] = C`
    class implements[P]:
        def __call__(self, cls: type[P]) -> type[P]:
            return cls

    class SomePropertyProtocol(Protocol): ...

    # Note that the decorator is not explicitly needed
    # in this example because the class is only used
    # for typing nested within another (decorated) class,
    # but it is still good for discipline
    @implements[SomePropertyProtocol]()
    # Note no inheritance; only a structural match
    class SomeProperty: ...

    class SomeProtocol(Protocol):
        @property
        def some_property(self) -> SomePropertyProtocol: ...

    # Auto-checks nested property types recursively
    @implements[SomeProtocol]()
    class Some:
        some_property: SomeProperty

    # Run this by a static type checker like mypy;
    # expect this to pass.
    ```

    This class serves architectural
    integrity and is not supposed
    to be instantiated.

    signed off: human
    """


class ComponentProtocol(EntityProtocol, Protocol):
    """An Acme component protocol."""

    class PropertyProtocol(EntityProtocol, Protocol):
        """
        Protocol for an Acme property of a component
        that defines a useful architectural detail.

        signed-off: human
        """

    class PortProtocol(EntityProtocol, Protocol):
        """
        Protocol for an Acme port on a component
        that is used by some connector.

        signed-off: human
        """

        class PropertyProtocol(EntityProtocol, Protocol):
            """
            Protocol for an Acme property of a port
            that defines a useful architectural detail.

            signed-off: human
            """


@final
class ConnectorProtocol(EntityProtocol, Protocol):
    """
    An Acme connector protocol.

    In this realization of Acme,
    connectors are not defined
    explicitly but rather are defined
    through downstream code that
    interacts with component ports
    and component and port properties.

    Therefore, this class
    cannot be subclassed.

    signed-off: human
    """
