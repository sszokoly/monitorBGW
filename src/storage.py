#!/usr/bin/env python
# -*- encoding: utf-8 -*-

############################## BEGIN IMPORTS ##################################

from abc import ABC, abstractmethod
from bisect import insort_left
from collections.abc import MutableMapping, ItemsView
from typing_extensions import Protocol

from typing import (
    AbstractSet,
    Any,
    Dict,
    Generic,
    ItemsView,
    Iterable,
    Iterator,
    List,
    Optional,
    Tuple,
    Union,
    TypeVar,
)

############################## END IMPORTS ####################################
############################## BEGIN VARIABLES ################################

class SupportsLessThan(Protocol):
    def __lt__(self, other: Any) -> bool:
        ...

K = TypeVar("K", bound=SupportsLessThan)
V = TypeVar("V")

############################## END VARIABLES ##################################
############################## BEGIN CLASSES ##################################

class AbstractRepository(ABC, Generic[K, V]):
    """Abstract key/value repository interface."""

    @abstractmethod
    def put(self, items: Dict[K, V]) -> None:
        """Insert or update multiple items."""
        raise NotImplementedError

    @abstractmethod
    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        """Return a single item by key or default."""
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> None:
        """Remove all items."""
        raise NotImplementedError

class SlicableOrderedDict(MutableMapping, Generic[K, V]):
    """
    Mutable mapping that keeps keys sorted and supports index/slice retrieval.

    Notes:
        - `__getitem__` supports:
          * int index -> V
          * slice -> List[V]
          * tuple(int,int) -> List[V]  (slice-like)
          * key -> V
    """

    def __init__(
        self,
        items: Optional[Dict[K, V]] = None,
        maxlen: Optional[int] = None,
        name: Optional[str] = None,
    ) -> None:
        self._items = dict(items) if items else {}  # type: Dict[K, V]
        self._keys = sorted(self._items.keys()) if items else []  # type: List[K]
        self.maxlen = maxlen
        self.name = name

    def __iter__(self) -> Iterator[K]:
        yield from self._keys

    def __getitem__(
        self,
        key: Union[int, slice, Tuple[int, int], K],
    ) -> Union[V, List[V]]:
        if isinstance(key, slice):
            idxs = range(len(self._items)).__getitem__(key)
            return [self._items[self._keys[i]] for i in idxs]

        if isinstance(key, tuple):
            idxs = range(len(self._items)).__getitem__(slice(*key))
            return [self._items[self._keys[i]] for i in idxs]

        if isinstance(key, int):
            if 0 <= key < len(self._items):
                return self._items[self._keys[key]]
            raise KeyError(key)

        return self._items[key]

    def __setitem__(self, key: K, item: V) -> None:
        if key in self._items:
            self._items[key] = item
            return

        if self.maxlen and len(self._items) == self.maxlen:
            first_key = self._keys.pop(0)
            del self._items[first_key]

        insort_left(self._keys, key)
        self._items[key] = item

    def __delitem__(self, key: K) -> None:
        if key not in self._items:
            raise KeyError(key)
        del self._items[key]
        self._keys.remove(key)

    def __contains__(self, key: Any) -> bool:
        return key in self._items

    def index(self, key: K) -> int:
        if key in self._keys:
            return self._keys.index(key)
        raise ValueError(key)

    def keys(self) -> AbstractSet[K]:
        return self._items.keys()

    def values(self) -> Iterable[V]:
        return self._items.values()

    def items(self) -> ItemsView:
        return self._items.items()

    def clear(self) -> None:
        self._items.clear()
        self._keys[:] = []

    def __len__(self) -> int:
        return len(self._items)

    def __repr__(self) -> str:
        return "{}({}, maxlen={})".format(
            type(self).__name__, self._items, self.maxlen
        )

class MemoryStorage(SlicableOrderedDict[K, V], AbstractRepository[K, V]):
    """
    In-memory repository with sorted keys.

    - Use `get(key)` for a single item (dict-like).
    - Use `select(...)` for range/index/slice retrieval.
    """

    def put(self, items: Dict[K, V]) -> None:
        for k, v in items.items():
            self[k] = v

    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        try:
            return self._items[key]
        except KeyError:
            return default

    def select(
        self,
        key: Union[slice, Tuple[int, int], int, K, None] = None,
    ) -> Union[V, List[V]]:
        """
        Retrieve by index/slice/tuple or key.
        If key is None, returns all values.
        """
        if key is None:
            key = slice(None, None)
        return self[key]

############################## END CLASSES ###################################

if __name__ == "__main__":
    storage = MemoryStorage(maxlen=3)
    storage.update({"1": "item1", "4": "item4", "2": "item2"})
    storage.update({"3": "item3"})
    print(storage.get("3"))
    print(storage.select((0,2)))
    print(storage.select(slice(0,2)))
    print(storage[0:2])
    print(storage.select(0))
    print(len(storage))
    print(storage.keys())
    print(repr(storage))
