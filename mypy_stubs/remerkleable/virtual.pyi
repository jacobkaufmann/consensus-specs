from remerkleable.tree import NavigationError as NavigationError, Node as Node, RebindableNode as RebindableNode, Root as Root
from typing import Any

class VirtualSource:
    def get_left(self, key: Root) -> Node: ...
    def get_right(self, key: Root) -> Node: ...
    def is_leaf(self, key: Root) -> bool: ...

class VirtualNode(RebindableNode, Node):
    def __init__(self, root: Root, src: VirtualSource) -> Any: ...
    def get_left(self) -> Node: ...
    def get_right(self) -> Node: ...
    def is_leaf(self) -> bool: ...
    @property
    def root(self) -> Root: ...
    def merkle_root(self) -> Root: ...
