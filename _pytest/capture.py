""" per-test stdout/stderr capturing mechanisms, ``capsys`` and ``capfd`` function arguments.  """

import pytest, py
import sys
import os

def pytest_addoption(parser):
    group = parser.getgroup("general")
    group._addoption('--capture', action="store", default=None,
        metavar="method", choices=['fd', 'sys', 'no'],
        help="per-test capturing method: one of fd (default)|sys|no.")
    group._addoption('-s', action="store_const", const="no", dest="capture",
        help="shortcut for --capture=no.")

@pytest.mark.tryfirst
def pytest_load_initial_conftests(early_config, parser, args, __multicall__):
    ns = parser.parse_known_args(args)
    method = ns.capture
    if not method:
        method = "fd"
    if method == "fd" and not hasattr(os, "dup"):
        method = "sys"
    capman = CaptureManager(method)
    early_config.pluginmanager.register(capman, "capturemanager")
    # make sure that capturemanager is properly reset at final shutdown
    def teardown():
        try:
            capman.reset_capturings()
        except ValueError:
            pass
    early_config.pluginmanager.add_shutdown(teardown)
    # make sure logging does not raise exceptions if it is imported
    def silence_logging_at_shutdown():
        if "logging" in sys.modules:
            sys.modules["logging"].raiseExceptions = False
    early_config.pluginmanager.add_shutdown(silence_logging_at_shutdown)

    # finally trigger conftest loading but while capturing (issue93)
    capman.resumecapture()
    try:
        try:
            return __multicall__.execute()
        finally:
            out, err = capman.suspendcapture()
    except:
        sys.stdout.write(out)
        sys.stderr.write(err)
        raise

def addouterr(rep, outerr):
    for secname, content in zip(["out", "err"], outerr):
        if content:
            rep.sections.append(("Captured std%s" % secname, content))

class NoCapture:
    def startall(self):
        pass
    def resume(self):
        pass
    def reset(self):
        pass
    def suspend(self):
        return "", ""

class CaptureManager:
    def __init__(self, defaultmethod=None):
        self._method2capture = {}
        self._defaultmethod = defaultmethod

    def _maketempfile(self):
        f = py.std.tempfile.TemporaryFile()
        newf = py.io.dupfile(f, encoding="UTF-8")
        f.close()
        return newf

    def _makestringio(self):
        return py.io.TextIO()

    def _getcapture(self, method):
        if method == "fd":
            return py.io.StdCaptureFD(now=False,
                out=self._maketempfile(), err=self._maketempfile()
            )
        elif method == "sys":
            return py.io.StdCapture(now=False,
                out=self._makestringio(), err=self._makestringio()
            )
        elif method == "no":
            return NoCapture()
        else:
            raise ValueError("unknown capturing method: %r" % method)

    def _getmethod(self, config, fspath):
        if config.option.capture:
            method = config.option.capture
        else:
            try:
                method = config._conftest.rget("option_capture", path=fspath)
            except KeyError:
                method = "fd"
        if method == "fd" and not hasattr(os, 'dup'): # e.g. jython
            method = "sys"
        return method

    def reset_capturings(self):
        for name, cap in self._method2capture.items():
            cap.reset()

    def resumecapture_item(self, item):
        method = self._getmethod(item.config, item.fspath)
        if not hasattr(item, 'outerr'):
            item.outerr = ('', '') # we accumulate outerr on the item
        return self.resumecapture(method)

    def resumecapture(self, method=None):
        if hasattr(self, '_capturing'):
            raise ValueError("cannot resume, already capturing with %r" %
                (self._capturing,))
        if method is None:
            method = self._defaultmethod
        cap = self._method2capture.get(method)
        self._capturing = method
        if cap is None:
            self._method2capture[method] = cap = self._getcapture(method)
            cap.startall()
        else:
            cap.resume()

    def suspendcapture(self, item=None):
        self.deactivate_funcargs()
        if hasattr(self, '_capturing'):
            method = self._capturing
            cap = self._method2capture.get(method)
            if cap is not None:
                outerr = cap.suspend()
            del self._capturing
            if item:
                outerr = (item.outerr[0] + outerr[0],
                          item.outerr[1] + outerr[1])
            return outerr
        if hasattr(item, 'outerr'):
            return item.outerr
        return "", ""

    def activate_funcargs(self, pyfuncitem):
        funcargs = getattr(pyfuncitem, "funcargs", None)
        if funcargs is not None:
            for name, capfuncarg in funcargs.items():
                if name in ('capsys', 'capfd'):
                    assert not hasattr(self, '_capturing_funcarg')
                    self._capturing_funcarg = capfuncarg
                    capfuncarg._start()

    def deactivate_funcargs(self):
        capturing_funcarg = getattr(self, '_capturing_funcarg', None)
        if capturing_funcarg:
            outerr = capturing_funcarg._finalize()
            del self._capturing_funcarg
            return outerr

    def pytest_make_collect_report(self, __multicall__, collector):
        method = self._getmethod(collector.config, collector.fspath)
        try:
            self.resumecapture(method)
        except ValueError:
            return # recursive collect, XXX refactor capturing
                   # to allow for more lightweight recursive capturing
        try:
            rep = __multicall__.execute()
        finally:
            outerr = self.suspendcapture()
        addouterr(rep, outerr)
        return rep

    @pytest.mark.tryfirst
    def pytest_runtest_setup(self, item):
        self.resumecapture_item(item)

    @pytest.mark.tryfirst
    def pytest_runtest_call(self, item):
        self.resumecapture_item(item)
        self.activate_funcargs(item)

    @pytest.mark.tryfirst
    def pytest_runtest_teardown(self, item):
        self.resumecapture_item(item)

    def pytest_keyboard_interrupt(self, excinfo):
        if hasattr(self, '_capturing'):
            self.suspendcapture()

    @pytest.mark.tryfirst
    def pytest_runtest_makereport(self, __multicall__, item, call):
        funcarg_outerr = self.deactivate_funcargs()
        rep = __multicall__.execute()
        outerr = self.suspendcapture(item)
        if funcarg_outerr is not None:
            outerr = (outerr[0] + funcarg_outerr[0],
                      outerr[1] + funcarg_outerr[1])
        addouterr(rep, outerr)
        if not rep.passed or rep.when == "teardown":
            outerr = ('', '')
        item.outerr = outerr
        return rep

error_capsysfderror = "cannot use capsys and capfd at the same time"

def pytest_funcarg__capsys(request):
    """enables capturing of writes to sys.stdout/sys.stderr and makes
    captured output available via ``capsys.readouterr()`` method calls
    which return a ``(out, err)`` tuple.
    """
    if "capfd" in request._funcargs:
        raise request.raiseerror(error_capsysfderror)
    return CaptureFixture(py.io.StdCapture)

def pytest_funcarg__capfd(request):
    """enables capturing of writes to file descriptors 1 and 2 and makes
    captured output available via ``capsys.readouterr()`` method calls
    which return a ``(out, err)`` tuple.
    """
    if "capsys" in request._funcargs:
        request.raiseerror(error_capsysfderror)
    if not hasattr(os, 'dup'):
        pytest.skip("capfd funcarg needs os.dup")
    return CaptureFixture(py.io.StdCaptureFD)

class CaptureFixture:
    def __init__(self, captureclass):
        self.capture = captureclass(now=False)

    def _start(self):
        self.capture.startall()

    def _finalize(self):
        if hasattr(self, 'capture'):
            outerr = self._outerr = self.capture.reset()
            del self.capture
            return outerr

    def readouterr(self):
        try:
            return self.capture.readouterr()
        except AttributeError:
            return self._outerr

    def close(self):
        self._finalize()
