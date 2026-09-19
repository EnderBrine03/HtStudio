"""PyQt5 yokken (ör. CI/sandbox) modülleri içe aktarabilmek için sahte PyQt5 modülleri."""
import sys
import types


class _Meta(type):
    def __getattr__(cls, name):
        if name.startswith("__"):
            raise AttributeError(name)
        v = _Dummy()
        setattr(cls, name, v)
        return v


class _Dummy(metaclass=_Meta):
    def __init__(self, *a, **k):
        pass

    def __call__(self, *a, **k):
        return _Dummy()

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _Dummy()

    def __or__(self, o):
        return self
    __ror__ = __and__ = __rand__ = __or__

    def __invert__(self):
        return self

    def __bool__(self):
        return False


def _pyqtSlot(*a, **k):
    return lambda f: f


def install():
    names = ["PyQt5", "PyQt5.QtCore", "PyQt5.QtGui", "PyQt5.QtWidgets", "PyQt5.QtWebChannel",
             "PyQt5.QtWebEngineCore", "PyQt5.QtWebEngineWidgets"]
    for n in names:
        m = types.ModuleType(n)
        cache = {}

        def getattr_(name, cache=cache):
            if name == "pyqtSlot":
                return _pyqtSlot
            if name.startswith("__"):
                raise AttributeError(name)
            if name not in cache:
                cache[name] = type(name, (_Dummy,), {})
            return cache[name]
        m.__getattr__ = getattr_
        sys.modules[n] = m
    sys.modules["PyQt5"].QtCore = sys.modules["PyQt5.QtCore"]
