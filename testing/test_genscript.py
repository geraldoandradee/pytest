import pytest
import py, os, sys
import subprocess


@pytest.fixture(scope="module")
def standalone(request):
    return Standalone(request)

class Standalone:
    def __init__(self, request):
        self.testdir = request.getfuncargvalue("testdir")
        script = "mypytest"
        result = self.testdir.runpytest("--genscript=%s" % script)
        assert result.ret == 0
        self.script = self.testdir.tmpdir.join(script)
        assert self.script.check()

    def run(self, anypython, testdir, *args):
        testdir.chdir()
        return testdir._run(anypython, self.script, *args)

def test_gen(testdir, anypython, standalone):
    if sys.version_info >= (2,7):
        result = testdir._run(anypython, "-c",
                                "import sys;print sys.version_info >=(2,7)")
        if result.stdout.str() == "False":
            pytest.skip("genscript called from python2.7 cannot work "
                        "earlier python versions")
    result = standalone.run(anypython, testdir, '--version')
    assert result.ret == 0
    result.stderr.fnmatch_lines([
        "*imported from*mypytest*"
    ])
    p = testdir.makepyfile("def test_func(): assert 0")
    result = standalone.run(anypython, testdir, p)
    assert result.ret != 0

def test_rundist(testdir, pytestconfig, standalone):
    pytestconfig.pluginmanager.skipifmissing("xdist")
    testdir.makepyfile("""
        def test_one():
            pass
    """)
    result = standalone.run(sys.executable, testdir, '-n', '3')
    assert result.ret == 0
    result.stdout.fnmatch_lines([
        "*1 passed*",
    ])
