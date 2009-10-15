"""
this little helper allows to run tests multiple times
in the same process.  useful for running tests from 
a console.
"""
import py, sys

def pytest(argv=None):
    if argv is None:
        argv = []
    try:
        sys.argv[1:] = argv
        py.cmdline.pytest()
    except SystemExit:
        pass
    # we need to reset the global py.test.config object
    py._com.comregistry = py._com.comregistry.__class__([])
    py.test.config = py.test.config.__class__(
        pluginmanager=py.test._PluginManager(py._com.comregistry))